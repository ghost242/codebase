import ast
import pytest

from codebase.code_parser.visitor import CodeVisitor
from codebase.code_graph.models import NodeType, GraphNode, Metadata


def test_invalid_project_root():
    # When project_root is empty, __init__ should raise a ValueError.
    with pytest.raises(ValueError):
        CodeVisitor(source_file="dummy.py", code="print('hello')", project_root="")


def test_module_node_creation(tmp_path):
    # Create a temporary file to simulate a module file.
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    source_file.write_text("'''Module docstring'''")
    code = source_file.read_text(encoding="utf-8")

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)

    # For a file named dummy.py, compute_package_full_path returns "dummy"
    # and simple name is "dummy" so module_id becomes "module:dummy.dummy".
    expected_module_id = "module:dummy.dummy"
    assert visitor.module_id == expected_module_id
    assert expected_module_id in visitor.graph_nodes


def test_visit_class_definition(tmp_path):
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = "'''Module Docstring'''\n\n" "class MyClass:\n" '    """MyClass docstring"""\n' "    pass\n"
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)
    tree = ast.parse(code)
    visitor.visit(tree)

    # The computed node id for the class should be "class:dummy.MyClass"
    class_id = "class:dummy.MyClass"
    assert class_id in visitor.graph_nodes
    class_node = visitor.graph_nodes[class_id]
    assert class_node.name == "MyClass"

    # Verify that the module node contains a 'contains' edge to the class node.
    module_node = visitor.graph_nodes[visitor.module_id]
    contains_edges = [
        edge
        for edge in module_node.relationships
        if edge.target_node_id == class_id and edge.edge_type.value == "contains"
    ]
    assert contains_edges, "Module node should have a 'contains' edge to the class node"


def test_visit_function_definition(tmp_path):
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = "'''Module Docstring'''\n\n" "def my_function():\n" '    """Function docstring"""\n' "    pass\n"
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)
    tree = ast.parse(code)
    visitor.visit(tree)

    # The computed node id for the function should be "function:dummy.my_function"
    function_id = "function:dummy.my_function"
    assert function_id in visitor.graph_nodes
    function_node = visitor.graph_nodes[function_id]
    assert function_node.name == "my_function"

    # Verify that the module node contains a 'contains' edge to the function node.
    module_node = visitor.graph_nodes[visitor.module_id]
    contains_edges = [
        edge
        for edge in module_node.relationships
        if edge.target_node_id == function_id and edge.edge_type.value == "contains"
    ]
    assert contains_edges, "Module node should have a 'contains' edge to the function node"


def test_visit_import(tmp_path):
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = "import os"
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)
    tree = ast.parse(code)
    visitor.visit(tree)

    # The visitor should create a module node for the imported 'os' module.
    imported_module_id = "module:os"
    assert imported_module_id in visitor.graph_nodes

    # Verify that the module node has an 'imports' edge to the os module.
    module_node = visitor.graph_nodes[visitor.module_id]
    import_edges = [
        edge
        for edge in module_node.relationships
        if edge.target_node_id == imported_module_id and edge.edge_type.value == "imports"
    ]
    assert import_edges, "Module node should have an 'imports' edge to the os module node"


def test_visit_call(tmp_path):
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = """
def my_function():
    pass

def caller():
    my_function()
"""
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)
    tree = ast.parse(code)
    visitor.visit(tree)

    my_function_id = "function:dummy.my_function"
    caller_id = "function:dummy.caller"
    assert my_function_id in visitor.graph_nodes
    assert caller_id in visitor.graph_nodes

    # Verify that the 'caller' function node has a 'calls' edge pointing to 'my_function'
    caller_node = visitor.graph_nodes[caller_id]
    call_edges = [
        edge
        for edge in caller_node.relationships
        if edge.edge_type.value == "calls" and edge.target_node_id == my_function_id
    ]
    assert call_edges, "Caller function should have a 'calls' edge to my_function"


def test_lookup_node(tmp_path):
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = "class MyClass:\n" "    pass\n\n" "def my_function():\n" "    pass\n"
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)
    tree = ast.parse(code)
    visitor.visit(tree)

    my_class_id = "class:dummy.MyClass"
    found_id = visitor.lookup_node("MyClass")
    assert found_id == my_class_id


def test_update_reference_table_replacement(tmp_path):
    # This test ensures that if two nodes with the same simple name are added,
    # the one with valid metadata (i.e. with a source_file) is preferred.
    project_root = str(tmp_path)
    source_file = tmp_path / "dummy.py"
    code = "pass"
    source_file.write_text(code)

    visitor = CodeVisitor(source_file=str(source_file), code=code, project_root=project_root)

    # Create a node without metadata.
    node_without_meta = GraphNode(
        id="function:dummy.no_meta", name="test_func", node_type=NodeType.FUNCTION, metadata=Metadata(source_file=None)
    )
    visitor.add_node(node_without_meta)

    # Create a node with metadata.
    node_with_meta = GraphNode(
        id="function:dummy.with_meta",
        name="test_func",
        node_type=NodeType.FUNCTION,
        metadata=Metadata(source_file=str(source_file)),
    )
    visitor.add_node(node_with_meta)

    # The lookup should return the node with metadata.
    found_id = visitor.lookup_node("test_func")
    assert found_id == "function:dummy.with_meta"
