import ast
import logging
import os
from pathlib import Path
from typing import Optional

import networkx as nx
import matplotlib.pyplot as plt
from neo4j import GraphDatabase

from codebase.code_graph.graph import CodeGraph
from codebase.code_parser.visitor import CodeVisitor


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper Functions (formerly in helpers.py)
# ---------------------------------------------------------------------------
def visualize_graph(graph: nx.DiGraph) -> None:
    """
    Visualizes a NetworkX graph with labels and relationships.
    """
    pos = nx.spring_layout(graph)
    labels = {node: f"{data['data']['node_type']}\n{data['data']['name']}" for node, data in graph.nodes(data=True)}
    nx.draw(graph, pos, labels=labels, with_labels=True, node_size=2000)
    edge_labels = {(u, v): d["relationship"] for u, v, d in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels)
    plt.show()


def dump_graph_to_neo4j(graph: nx.DiGraph, uri: str, user: str, password: str, *, cleanup: bool = False) -> None:
    """
    Dumps a NetworkX graph to a Neo4j database.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        if cleanup:
            session.run("MATCH (n) DETACH DELETE n")
        for node_id, attr in graph.nodes(data=True):
            data = attr.get("data", {})
            if not data:
                continue
            label = data.get("node_type", "Unknown").capitalize()
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
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "node_type": data.get("node_type"),
                    "source_file": data.get("metadata", {}).get("source_file"),
                    "docstring": data.get("metadata", {}).get("docstring"),
                    "line_start": data.get("metadata", {}).get("line_start"),
                    "line_end": data.get("metadata", {}).get("line_end"),
                    "type_hint": data.get("metadata", {}).get("type_hint"),
                },
            )
        for u, v, edge_attr in graph.edges(data=True):
            rel = edge_attr.get("relationship")
            if rel:
                # It's good to restrict the allowed relationship types if possible.
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


def build_from_code(source_file: str, code: str, project_root: str = "") -> CodeGraph:
    """
    Parses the provided code using CodeVisitor and builds a CodeGraph.
    """
    tree = ast.parse(code)
    visitor = CodeVisitor(source_file=source_file, code=code, project_root=project_root)
    visitor.visit(tree)
    cg = CodeGraph()
    cg.build_from_nodes(visitor.get_graph_nodes())
    return cg


def read_python_file(filepath: Path) -> Optional[str]:
    """Reads a Python file and returns its content; handles errors gracefully."""
    try:
        return filepath.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError) as e:
        logger.error(f"[read_python_file] Skipping {filepath}: {e}")
        return None


def merge_graphs(master: CodeGraph, module_graph: CodeGraph) -> None:
    """Merges a module-level CodeGraph into a master project-wide CodeGraph."""
    module_nx_graph = module_graph.get_networkx_graph()
    for node_id, attr in module_nx_graph.nodes(data=True):
        node_data = attr.get("data", attr)
        master.graph.add_node(node_id, data=node_data)
    for u, v, edge_attr in module_nx_graph.edges(data=True):
        master.graph.add_edge(u, v, relationship=edge_attr.get("relationship", ""))


def build_project_graph(project_path: str) -> CodeGraph:
    """
    Builds a CodeGraph for an entire project directory by parsing all Python files.
    """
    master = CodeGraph()
    root = Path(project_path)
    print(f"[build_project_graph] Root directory: {root}")
    for filepath in root.rglob("*.py"):
        print(f"[build_project_graph] Processing {filepath}")
        code = read_python_file(filepath)
        if code is None:
            continue
        module_graph = build_from_code(str(filepath), code, project_root=str(root))
        merge_graphs(master, module_graph)
    master.merge_nodes_by_reference()
    return master
