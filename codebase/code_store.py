"""
Module: code_store.py
Description: Provides functions to store, update, and synchronize a NetworkX graph
             representing your codebase with a Neo4j graph database. This module
             merges nodes and edges (using MERGE with ON MATCH SET/ON CREATE SET)
             and also deletes nodes and edges that are not present in the new graph.
Environment: Docker container
Command: 
    ``` shell
    $ docker run \
        --restart always \
        --publish=7474:7474 --publish=7687:7687 \
        --env NEO4J_AUTH=neo4j/devpassword \
        --volume=neo4j:/data \
        -d neo4j
    ```
"""

import os
import networkx as nx
from neo4j import GraphDatabase, Driver
import logging

# Neo4j driver initialization (no auth version)
URI = "bolt://localhost:7687"
USERNAME = os.getenv("GRAPHDB_USERNAME", "neo4j")
PASSWORD = os.getenv("GRAPHDB_PASSWORD", "devpassword")

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


def create_project_database(driver: Driver, project_name: str) -> None:
    """
    Creates a new Neo4j database for the specified project if it does not already exist.

    This function connects to the "system" database and checks whether a database with the given
    project name exists. If the database does not exist, it issues a command to create it.

    Args:
        driver (neo4j.Driver): An instance of the Neo4j driver.
        project_name (str): The name of the project to use as the database name.
    """
    with driver.session(database="system") as session:
        result = session.run("SHOW DATABASES")
        exists = any(record["name"] == project_name for record in result)
        if exists:
            logging.info(f"Database '{project_name}' already exists.")
        else:
            session.run(f"CREATE DATABASE {project_name}")
            logging.info(f"Database '{project_name}' has been created.")

# -----------------------------------------------------------------------------
# Merge (store/update) functions for nodes and edges.
# -----------------------------------------------------------------------------
def store_graph_in_neo4j(tx, nx_graph: nx.DiGraph):
    # Merge/update nodes.
    for node_id, data in nx_graph.nodes(data=True):
        query = """
        MERGE (n:Node {id: $id})
        ON MATCH SET n.name = coalesce($name, n.name),
                      n.node_type = coalesce($node_type, n.node_type),
                      n.data_type = coalesce($data_type, n.data_type),
                      n.parent_id = coalesce($parent_id, n.parent_id),
                      n.docstring = coalesce($docstring, n.docstring),
                      n.file = coalesce($file, n.file)
        ON CREATE SET n.name = $name,
                      n.node_type = $node_type,
                      n.data_type = $data_type,
                      n.parent_id = $parent_id,
                      n.docstring = $docstring,
                      n.file = $file
        """
        tx.run(
            query,
            id=node_id,
            name=data.get("name"),
            node_type=data.get("type"),
            data_type=data.get("data_type", "Unknown"),
            parent_id=data.get("parent_id", ""),
            docstring=data.get("docstring", ""),
            file=data.get("file", "")
        )
    # Merge/update edges.
    for source, destination, data in nx_graph.edges(data=True):
        query = """
        MATCH (a:Node {id: $source})
        MATCH (b:Node {id: $destination})
        MERGE (a)-[r:RELATION {source: $source, destination: $destination}]->(b)
        ON MATCH SET r.op = coalesce($op, r.op)
        ON CREATE SET r.op = $op
        """
        tx.run(
            query,
            source=source,
            destination=destination,
            op=data.get("op", "")
        )

# -----------------------------------------------------------------------------
# Functions to retrieve existing nodes and edges.
# -----------------------------------------------------------------------------
def get_existing_node_ids(tx):
    query = "MATCH (n:Node) RETURN n.id AS id"
    result = tx.run(query)
    return {record["id"] for record in result}

def get_existing_edges(tx):
    """
    Returns a set of tuples (source, destination, op) for all relationships.
    """
    query = "MATCH (a:Node)-[r:RELATION]->(b:Node) RETURN r.source AS source, r.destination AS destination, r.op AS op"
    result = tx.run(query)
    return {(record["source"], record["destination"], record["op"]) for record in result}

# -----------------------------------------------------------------------------
# Delete functions for nodes and edges.
# -----------------------------------------------------------------------------
def delete_node(tx, node_id: str):
    query = "MATCH (n:Node {id: $id}) DETACH DELETE n"
    tx.run(query, id=node_id)

def delete_edge(tx, source: str, destination: str):
    query = """
    MATCH (a:Node {id: $source})-[r:RELATION]->(b:Node {id: $destination})
    DELETE r
    """
    tx.run(query, source=source, destination=destination)

# -----------------------------------------------------------------------------
# High-level functions for storing and synchronizing the graph.
# -----------------------------------------------------------------------------
def store_networkx_graph(nx_graph: nx.DiGraph, driver):
    with driver.session() as session:
        session.execute_write(store_graph_in_neo4j, nx_graph)
    print("Graph stored in Neo4j successfully.")

def sync_graph(new_graph: nx.DiGraph, driver: Driver, project_name: str) -> None:
    """
    Synchronize the Neo4j database with the provided NetworkX graph.
    This function merges nodes and edges from new_graph into the Neo4j database for the specified project,
    and deletes any nodes or edges that exist in the database but not in new_graph.

    Args:
        new_graph (nx.DiGraph): The new code graph.
        driver (neo4j.Driver): The Neo4j driver.
        project_name (str): The name of the project, which is used as the Neo4j database name.
    """
    # Ensure the project-specific database exists.
    # create_project_database(driver, project_name)

    # Open a session on the project-specific database.
    with driver.session(database="neo4j") as session:
        # Merge/update nodes and edges.
        session.execute_write(store_graph_in_neo4j, new_graph)

        # Delete nodes not in new_graph.
        existing_node_ids = session.execute_read(get_existing_node_ids)
        new_node_ids = set(new_graph.nodes())
        nodes_to_delete = existing_node_ids - new_node_ids
        for node_id in nodes_to_delete:
            session.execute_write(delete_node, node_id)

        # Delete edges not in new_graph.
        existing_edges = session.execute_read(get_existing_edges)
        new_edges = {(s, d, data.get("op", "")) for s, d, data in new_graph.edges(data=True)}
        edges_to_delete = existing_edges - new_edges
        for source, destination, _ in edges_to_delete:
            session.execute_write(delete_edge, source, destination)

        print("Graph synchronized with Neo4j.")
