import os
from pathlib import Path
from typing import Optional
from codebase.code_parser.code_graph import (
    CodeGraph,
)  # Importing CodeGraph from its module


def read_python_file(filepath: Path) -> Optional[str]:
    """Reads a Python file and returns its content, handling errors gracefully."""
    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[read_python_file] Skipping {filepath}: {e}")
        return None


def merge_graphs(master: CodeGraph, module_graph: CodeGraph) -> None:
    """Merges a module-level CodeGraph into the master project-wide CodeGraph."""
    module_nx_graph = module_graph.get_networkx_graph()

    # Add nodes from the module graph
    for node_id, attr in module_nx_graph.nodes(data=True):
        node_data = attr.get("data", attr)  # Ensure compatibility
        master.graph.add_node(node_id, data=node_data)

    # Add edges from the module graph
    for u, v, edge_attr in module_nx_graph.edges(data=True):
        master.graph.add_edge(u, v, relationship=edge_attr.get("relationship", ""))


def build_project_graph(project_path: str) -> CodeGraph:
    """
    Builds a CodeGraph for an entire project directory by parsing all Python files.

    Args:
        project_path (str): The root directory of the project.

    Returns:
        CodeGraph: A graph representation of the project's code structure.
    """
    master = CodeGraph()
    root = Path(project_path)
    print(f"[build_project_graph] root directory {root}")

    for filepath in root.rglob("*.py"):
        print(f"[build_project_graph] Processing {filepath}")

        code = read_python_file(filepath)
        if code is None:
            continue

        module_graph = CodeGraph().build_from_code(
            str(filepath), code, project_root=str(root)
        )
        merge_graphs(master, module_graph)

    master.merge_nodes_by_reference()
    return master


if __name__ == "__main__":
    # Set the root directory of your package project here.
    project_directory = "/Users/jeffrey/Playground/sqlalchemy/lib"
    project_graph = build_project_graph(project_directory)
    project_graph.dump_to_neo4j(
        uri="bolt://localhost:7687", user="neo4j", password="devpassword"
    )
