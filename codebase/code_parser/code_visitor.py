import ast
import os
from typing import List, Dict, Optional, Set

from codebase.code_parser.helpers import (
    compute_package_full_path,
)  # Import the helper function
from codebase.code_parser.models import (
    NodeType,
    EdgeType,
    GraphNode,
    GraphEdge,
    Metadata,
)  # Import from your module


class CodeVisitor(ast.NodeVisitor):
    def __init__(self, source_file: str, code: str, project_root: str):
        if not project_root:
            raise ValueError("project_root must be provided to compute package paths")

        self.source_file = source_file
        self.code = code
        self.project_root = project_root
        self.graph_nodes: Dict[str, GraphNode] = {}
        self.current_parent_ids: List[str] = []
        self.reference_table: Dict[str, Dict[str, str]] = {}
        self.imported_module_cache: Dict[str, str] = {}
        self.handled_call_nodes: Set[ast.Call] = set()

        # Compute module ID
        filename = os.path.basename(source_file)
        simple_name = (
            os.path.basename(os.path.dirname(source_file))
            if filename == "__init__.py"
            else os.path.splitext(filename)[0]
        )
        package_full = compute_package_full_path(source_file, project_root)
        self.module_id = f"module:{package_full}.{simple_name}"

        # Create module node
        module_node = GraphNode(
            id=self.module_id,
            name=simple_name,
            node_type=NodeType.MODULE,
            metadata=Metadata(
                source_file=source_file, docstring=ast.get_docstring(ast.parse(code))
            ),
        )
        self.graph_nodes[self.module_id] = module_node
        self.update_reference_table(module_node)
        self.current_parent_ids.append(self.module_id)
        print(f"[__init__] Initialized CodeVisitor for module_id: {self.module_id}")

    def update_reference_table(self, node: GraphNode) -> None:
        """Updates the reference table with a new node entry."""
        try:
            _, full = node.id.split(":", 1)
            package = full.rsplit(".", 1)[0]
        except ValueError:
            package = ""

        if node.name not in self.reference_table:
            self.reference_table[node.name] = {}

        existing_node_id = self.reference_table[node.name].get(package)
        if existing_node_id:
            existing_node = self.graph_nodes.get(existing_node_id)

            # ✅ Only replace if the new node has a source file (ensuring better metadata)
            if (
                existing_node is None
                or not (existing_node.metadata and existing_node.metadata.source_file)
            ) and (node.metadata and node.metadata.source_file):
                self.reference_table[node.name][package] = node.id
                print(
                    f"[update_reference_table] Replaced '{node.name}' in '{package}' with '{node.id}' (better metadata)"
                )
        else:
            self.reference_table[node.name][package] = node.id
            print(
                f"[update_reference_table] Added '{node.id}' for '{node.name}' in package '{package}'"
            )

    def compute_node_id(self, node_type: NodeType, name: str) -> str:
        """Computes a unique node ID based on its type and parent context."""
        if not self.current_parent_ids:
            raise ValueError("No parent found when computing node id.")

        parent_id = self.current_parent_ids[-1]
        try:
            _, full = parent_id.split(":", 1)
            package_path = full.rsplit(".", 1)[0]
        except ValueError:
            package_path = ""

        computed_id = f"{node_type.value}:{package_path}.{name}"
        print(f"[compute_node_id] Computed node id '{computed_id}'")
        return computed_id

    def add_node(self, node: GraphNode) -> None:
        """Adds a node to the graph and updates references."""
        node_data = node.model_dump()
        node_data["node_type"] = node.node_type.value

        for rel in node_data.get("relationships", []):
            if isinstance(rel.get("edge_type"), EdgeType):
                rel["edge_type"] = rel["edge_type"].value

        self.graph_nodes[node.id] = node
        self.update_reference_table(node)

        if self.current_parent_ids:
            parent_id = self.current_parent_ids[-1]
            contains_edge = GraphEdge(
                edge_type=EdgeType.CONTAINS,
                source_node_id=parent_id,
                target_node_id=node.id,
                source_node_type=self.graph_nodes[parent_id].node_type,
                target_node_type=node.node_type,
            )
            self.graph_nodes[parent_id].relationships.append(contains_edge)

    def visit_Import(self, node: ast.Import):
        """Handles module imports and updates the graph."""
        for alias in node.names:
            imported_module = alias.name
            imported_module_id = self.imported_module_cache.get(
                imported_module, f"module:{imported_module}"
            )
            self.imported_module_cache[imported_module] = imported_module_id

            if imported_module_id not in self.graph_nodes:
                self.graph_nodes[imported_module_id] = GraphNode(
                    id=imported_module_id,
                    name=imported_module,
                    node_type=NodeType.MODULE,
                    metadata=Metadata(source_file=None, docstring=None),
                )
                self.update_reference_table(self.graph_nodes[imported_module_id])

            self.graph_nodes[self.module_id].relationships.append(
                GraphEdge(
                    edge_type=EdgeType.IMPORTS,
                    source_node_id=self.module_id,
                    target_node_id=imported_module_id,
                    source_node_type=NodeType.MODULE,
                    target_node_type=NodeType.MODULE,
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef):
        """Handles class definitions and prevents duplicate class nodes using the reference table."""
        class_id = self.compute_node_id(NodeType.CLASS, node.name)

        # ✅ Check the reference table before adding the node
        existing_node_id = self.lookup_node(node.name)
        if existing_node_id:
            print(
                f"[visit_ClassDef] Using existing node '{existing_node_id}' instead of creating '{class_id}'"
            )
            return

        class_node = GraphNode(
            id=class_id,
            name=node.name,
            node_type=NodeType.CLASS,
            metadata=Metadata(
                source_file=self.source_file,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", None),
                docstring=ast.get_docstring(node),
            ),
        )

        self.add_node(class_node)
        self.current_parent_ids.append(class_id)
        self.generic_visit(node)
        self.current_parent_ids.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Handles function definitions and prevents duplicate function nodes using the reference table."""
        function_id = self.compute_node_id(NodeType.FUNCTION, node.name)

        # ✅ Check the reference table before adding the node
        existing_node_id = self.lookup_node(node.name)
        if existing_node_id:
            print(
                f"[visit_FunctionDef] Using existing node '{existing_node_id}' instead of creating '{function_id}'"
            )
            return

        function_node = GraphNode(
            id=function_id,
            name=node.name,
            node_type=NodeType.FUNCTION,
            metadata=Metadata(
                source_file=self.source_file,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", None),
                docstring=ast.get_docstring(node),
            ),
        )

        self.add_node(function_node)
        self.current_parent_ids.append(function_id)
        self.generic_visit(node)
        self.current_parent_ids.pop()

    def visit_Call(self, node: ast.Call):
        """Handles function calls and adds edges."""
        if node in self.handled_call_nodes:
            return self.generic_visit(node)

        caller_id = next(
            (p for p in reversed(self.current_parent_ids) if p.startswith("function:")),
            self.module_id,
        )
        called_function_id = None

        if isinstance(node.func, ast.Name):
            called_function_id = self.lookup_node(node.func.id) or self.compute_node_id(
                NodeType.FUNCTION, node.func.id
            )
        elif isinstance(node.func, ast.Attribute):
            called_function_id = self.lookup_node(
                node.func.attr
            ) or self.compute_node_id(NodeType.FUNCTION, node.func.attr)

        if called_function_id:
            self.graph_nodes[caller_id].relationships.append(
                GraphEdge(
                    edge_type=EdgeType.CALLS,
                    source_node_id=caller_id,
                    target_node_id=called_function_id,
                    source_node_type=NodeType.FUNCTION,
                    target_node_type=NodeType.FUNCTION,
                )
            )

        self.generic_visit(node)

    def get_graph_nodes(self) -> List[GraphNode]:
        """Returns all collected graph nodes."""
        return list(self.graph_nodes.values())

    def lookup_node(self, simple_name: str) -> Optional[str]:
        """Looks up a node ID by its simple name using the reference table."""
        candidates = self.reference_table.get(simple_name, {})
        if not candidates:
            print(f"[lookup_node] No candidates found for '{simple_name}'")
            return None

        best_id = None
        best_score = -1

        for package, node_id in candidates.items():
            node = self.graph_nodes.get(node_id)
            score = 1 if (node and node.metadata and node.metadata.source_file) else 0

            # ✅ Prefer nodes with metadata, and prioritize shorter package paths
            if score > best_score or (
                score == best_score
                and (
                    best_id is None
                    or package < best_id.split(":", 1)[1].rsplit(".", 1)[0]
                )
            ):
                best_score = score
                best_id = node_id

        print(
            f"[lookup_node] Resolved '{simple_name}' to '{best_id}' with score {best_score}"
        )
        return best_id
