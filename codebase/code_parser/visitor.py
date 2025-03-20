import ast
import os
from typing import List, Dict, Optional, Set

from codebase.code_parser.utils import (
    compute_package_full_path,
    find_package_source,  # New helper to locate a module's source file.
)  # Import the helper function
from codebase.code_graph.models import (
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
        self.decorator_mappings: Dict[str, List[str]] = {}  # Track decorators per node
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
            metadata=Metadata(source_file=source_file, docstring=ast.get_docstring(ast.parse(code))),
        )
        self.graph_nodes[self.module_id] = module_node
        self.update_reference_table(module_node)
        self.current_parent_ids.append(self.module_id)
        print(f"[__init__] Initialized CodeVisitor for module_id: {self.module_id}")

    def update_reference_table(self, node: GraphNode) -> None:
        """Ensures reference table only updates when necessary."""
        try:
            _, full = node.id.split(":", 1)
            package = full.rsplit(".", 1)[0]
        except ValueError:
            package = ""

        if node.name not in self.reference_table:
            self.reference_table[node.name] = {}

        existing_node_id = self.reference_table[node.name].get(package)
        if existing_node_id and existing_node_id in self.graph_nodes:
            existing_node = self.graph_nodes[existing_node_id]
            # Keep the existing node if it has better metadata
            if existing_node.metadata and existing_node.metadata.source_file:
                print(f"[update_reference_table] Skipping '{node.name}' update: existing node has better metadata.")
                return

        self.reference_table[node.name][package] = node.id
        print(f"[update_reference_table] Added '{node.id}' for '{node.name}' in package '{package}'")

    def compute_node_id(self, node_type: NodeType, name: str) -> str:
        """Computes a unique node ID based on its type and parent context."""
        if not self.current_parent_ids:
            print("[compute_node_id] Warning: No parent found, using module as fallback.")
            return f"{node_type.value}:{self.module_id}.{name}"

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
            imported_module_id = self.imported_module_cache.get(imported_module, f"module:{imported_module}")
            self.imported_module_cache[imported_module] = imported_module_id

            # Use find_package_source to locate the module's source file if available.
            module_source_file = find_package_source(imported_module)

            if imported_module_id not in self.graph_nodes:
                self.graph_nodes[imported_module_id] = GraphNode(
                    id=imported_module_id,
                    name=imported_module,
                    node_type=NodeType.MODULE,
                    metadata=Metadata(source_file=module_source_file, docstring=None),
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

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """
        Handles 'from X import Y' statements.
        Computes the full module name (taking into account relative imports),
        uses find_package_source to locate the module's source file, and adds
        an IMPORTS edge from the current module to the imported module.
        """
        # Compute the base module name, taking into account relative import levels.
        if node.level > 0:
            try:
                # Extract the package parts from the current module id.
                _, full = self.module_id.split(":", 1)
                package_parts = full.split(".")
            except Exception:
                package_parts = []
            # Navigate up 'node.level' levels.
            base = ".".join(package_parts[: -node.level])
            base_module = base + ("." + node.module if node.module else "")
        else:
            base_module = node.module if node.module else ""

        for alias in node.names:
            # Form the full module name by appending the alias.
            if base_module:
                imported_module = base_module + "." + alias.name
            else:
                imported_module = alias.name

            imported_module_id = self.imported_module_cache.get(imported_module, f"module:{imported_module}")
            self.imported_module_cache[imported_module] = imported_module_id

            # Use the helper to find the source file for the module.
            module_source_file = find_package_source(imported_module)
            if imported_module_id not in self.graph_nodes:
                self.graph_nodes[imported_module_id] = GraphNode(
                    id=imported_module_id,
                    name=imported_module,
                    node_type=NodeType.MODULE,
                    metadata=Metadata(source_file=module_source_file, docstring=None),
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
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Handles class definitions and prevents duplicate class nodes using the reference table."""
        class_id = self.compute_node_id(NodeType.CLASS, node.name)

        # Check if the class already exists in the reference table
        existing_node_id = self.lookup_node(node.name)
        if existing_node_id:
            print(f"[visit_ClassDef] Using existing node '{existing_node_id}' instead of creating '{class_id}'")
            return

        # Check if the class defines __call__
        is_callable = any(
            isinstance(body_item, ast.FunctionDef) and body_item.name == "__call__" for body_item in node.body
        )

        # Extract base classes
        base_classes = []
        for base in node.bases:
            try:
                base_str = ast.unparse(base) if hasattr(ast, "unparse") else str(base)
            except Exception:
                base_str = str(base)
            base_classes.append(base_str)

        class_node = GraphNode(
            id=class_id,
            name=node.name,
            node_type=NodeType.CLASS,
            metadata=Metadata(
                source_file=self.source_file,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", None),
                docstring=ast.get_docstring(node),
                additional={"base_classes": base_classes, "is_callable": is_callable},  # Store base classes in metadata
            ),
        )

        self.add_node(class_node)

        # Ensure methods and attributes are associated with this class
        self.current_parent_ids.append(class_id)

        # Handle decorators first to establish DECORATES relationships
        self.handle_decorators(node, class_id)

        # Visit class body (functions, variables, inner classes)
        self.generic_visit(node)

        # Restore parent context after processing the class
        self.current_parent_ids.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Handles function definitions and ensures methods belong to their parent class if applicable."""

        # Determine if this function is inside a class (i.e., a method)
        parent_id = self.current_parent_ids[-1] if self.current_parent_ids else self.module_id
        is_method = parent_id.startswith("class:")

        # Compute function/method ID
        function_id = self.compute_node_id(NodeType.FUNCTION, node.name)

        # Check if the function already exists in the reference table
        existing_node_id = self.lookup_node(node.name)
        if existing_node_id:
            print(f"[visit_FunctionDef] Using existing node '{existing_node_id}' instead of creating '{function_id}'")
            return

        # Create function/method node
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

        # Set method-parent association
        if is_method:
            method_edge = GraphEdge(
                edge_type=EdgeType.CONTAINS,
                source_node_id=parent_id,  # The class containing the method
                target_node_id=function_id,
                source_node_type=NodeType.CLASS,
                target_node_type=NodeType.FUNCTION,
            )
            self.graph_nodes[parent_id].relationships.append(method_edge)

        # Mark the function as the current parent (for possible nested functions)
        self.current_parent_ids.append(function_id)

        # Handle decorators before processing function body
        self.handle_decorators(node, function_id)

        # Visit the function body
        self.generic_visit(node)

        # Restore parent context after processing function
        self.current_parent_ids.pop()

    def visit_Call(self, node: ast.Call):
        """Handles function/method calls and ensures calls to callable classes are tracked."""
        if node in self.handled_call_nodes:
            return self.generic_visit(node)

        caller_id = next(
            (p for p in reversed(self.current_parent_ids) if p.startswith("function:")),
            self.module_id,
        )
        called_function_id = None

        if isinstance(node.func, ast.Name):
            # Check if function name refers to a callable class
            possible_class_id = self.lookup_node(node.func.id) or self.compute_node_id(NodeType.CLASS, node.func.id)

            if possible_class_id in self.graph_nodes and self.graph_nodes[possible_class_id].metadata:
                node_metadata = self.graph_nodes[possible_class_id].metadata
                if node_metadata.additional and node_metadata.additional.get("is_callable"):
                    called_function_id = possible_class_id  # Redirect call to the class itself
                else:
                    called_function_id = self.lookup_node(node.func.id) or self.compute_node_id(NodeType.FUNCTION, node.func.id)

        elif isinstance(node.func, ast.Attribute):
            # Handle method calls (e.g., `obj.method()`)
            attr_name = node.func.attr
            obj_name = node.func.value.id if isinstance(node.func.value, ast.Name) else None

            if obj_name and obj_name in ("self", "cls"):  # Likely a method on the same class
                parent_class_id = next((p for p in reversed(self.current_parent_ids) if p.startswith("class:")), None)
                if parent_class_id:
                    called_function_id = f"function:{parent_class_id.split(':', 1)[1]}.{attr_name}"
            else:
                # Check if the object itself is a callable class
                possible_class_id = self.lookup_node(obj_name) or self.compute_node_id(NodeType.CLASS, obj_name)

                if possible_class_id in self.graph_nodes:
                    node_metadata = self.graph_nodes[possible_class_id].metadata
                    if node_metadata and node_metadata.additional and node_metadata.additional.get("is_callable"):
                        called_function_id = possible_class_id  # Redirect call to the class itself

        if called_function_id:
            self.graph_nodes[caller_id].relationships.append(
                GraphEdge(
                    edge_type=EdgeType.CALLS,
                    source_node_id=caller_id,
                    target_node_id=called_function_id,
                    source_node_type=NodeType.FUNCTION,
                    target_node_type=NodeType.CLASS if called_function_id.startswith("class:") else NodeType.FUNCTION,
                )
            )

        self.generic_visit(node)

    def handle_decorators(self, node: ast.AST, target_id: str):
        """Extracts decorators and creates DECORATES edges while resolving full decorator paths."""
        if not hasattr(node, "decorator_list"):
            return

        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorator_name = decorator.id
                full_decorator_id = self.lookup_node(decorator_name) or self.compute_node_id(
                    NodeType.FUNCTION, decorator_name
                )

            elif isinstance(decorator, ast.Attribute):
                decorator_name = decorator.attr
                obj_name = decorator.value.id if isinstance(decorator.value, ast.Name) else None
                full_decorator_id = self.lookup_node(f"{obj_name}.{decorator_name}") or self.compute_node_id(
                    NodeType.FUNCTION, decorator_name
                )

            else:
                continue

            # Determine target type based on its ID prefix
            target_node_type = NodeType.FUNCTION if target_id.startswith("function:") else NodeType.CLASS

            decorates_edge = GraphEdge(
                edge_type=EdgeType.DECORATES,
                source_node_id=full_decorator_id,
                target_node_id=target_id,
                source_node_type=NodeType.FUNCTION,
                target_node_type=target_node_type,
            )
            self.graph_nodes[target_id].relationships.append(decorates_edge)

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
                score == best_score and (best_id is None or package < best_id.split(":", 1)[1].rsplit(".", 1)[0])
            ):
                best_score = score
                best_id = node_id

        print(f"[lookup_node] Resolved '{simple_name}' to '{best_id}' with score {best_score}")
        return best_id
