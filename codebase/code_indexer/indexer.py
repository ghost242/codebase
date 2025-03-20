import ast
import os
from typing import List

from codebase.code_parser.visitor import CodeVisitor
from codebase.code_graph.models import GraphNode

def extract_code_components(source_file: str, code: str, project_root: str) -> List[GraphNode]:
    """
    Extracts code components from the provided source code file using the CodeVisitor.
    
    Args:
        source_file (str): Path to the source code file.
        code (str): The source code as a string.
        project_root (str): The root directory of the project (used for computing package paths).
        
    Returns:
        List[GraphNode]: A list of GraphNode objects representing the extracted code components.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        print(f"Syntax error while parsing {source_file}: {e}")
        return []

    # Initialize the CodeVisitor to extract components with enriched metadata.
    visitor = CodeVisitor(source_file=source_file, code=code, project_root=project_root)
    visitor.visit(tree)
    return visitor.get_graph_nodes()


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python indexer.py <source_file> <project_root>")
        sys.exit(1)

    source_file = sys.argv[1]
    project_root = sys.argv[2]

    if not os.path.isfile(source_file):
        print(f"Error: File '{source_file}' not found.")
        sys.exit(1)

    with open(source_file, "r", encoding="utf-8") as f:
        code_content = f.read()

    nodes = extract_code_components(source_file, code_content, project_root)

    # Output each node as JSON for easy inspection.
    for node in nodes:
        print(node.json(indent=2))
