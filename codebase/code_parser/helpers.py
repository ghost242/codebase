import os

import networkx as nx
import matplotlib.pyplot as plt

from neo4j import GraphDatabase


def compute_package_full_path(source_file: str, project_root: str) -> str:
    """
    Computes the package full path from a source file relative to the project root.

    Args:
        source_file (str): The absolute or relative path of the source file.
        project_root (str): The root directory of the project.

    Returns:
        str: The computed package path in dot notation.
    """
    rel_path = os.path.relpath(source_file, project_root)
    norm_path = os.path.normpath(rel_path)
    parts = norm_path.split(os.sep)

    # Remove __init__.py for package directories, otherwise strip file extension.
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = os.path.splitext(parts[-1])[0]

    return ".".join(parts)


def visualize_graph(graph: nx.DiGraph) -> None:
    """Visualizes a NetworkX graph with labels and relationships."""
    pos = nx.spring_layout(graph)
    labels = {
        node: f"{data['data']['node_type']}\n{data['data']['name']}"
        for node, data in graph.nodes(data=True)
    }
    nx.draw(graph, pos, labels=labels, with_labels=True, node_size=2000)
    edge_labels = {(u, v): d["relationship"] for u, v, d in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels)
    plt.show()


def dump_graph_to_neo4j(graph: nx.DiGraph, uri: str, user: str, password: str) -> None:
    """Dumps a NetworkX graph to a Neo4j database."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")  # Clear existing graph

        # Add nodes
        for node_id, attr in graph.nodes(data=True):
            data = attr.get("data", {})
            if not data:
                continue
            label = data["node_type"].capitalize()
            session.run(
                f"""
                CREATE (n:{label} {{
                    id: $id, name: $name, node_type: $node_type,
                    source_file: $source_file, docstring: $docstring,
                    line_start: $line_start, line_end: $line_end,
                    type_hint: $type_hint
                }})
                """,
                **{
                    "id": data["id"],
                    "name": data["name"],
                    "node_type": data["node_type"],
                    "source_file": data.get("metadata", {}).get("source_file"),
                    "docstring": data.get("metadata", {}).get("docstring"),
                    "line_start": data.get("metadata", {}).get("line_start"),
                    "line_end": data.get("metadata", {}).get("line_end"),
                    "type_hint": data.get("metadata", {}).get("type_hint"),
                },
            )

        # Add relationships
        for u, v, d in graph.edges(data=True):
            rel = d.get("relationship")
            if rel:
                session.run(
                    """
                    MATCH (a {id: $source_id}), (b {id: $target_id})
                    CREATE (a)-[r:%s]->(b)
                    """
                    % rel.upper(),
                    source_id=u,
                    target_id=v,
                )
    driver.close()
