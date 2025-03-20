import ast
import sys
from pathlib import Path

import networkx as nx
from matplotlib import pyplot as plt
from neo4j import GraphDatabase

from codebase.code_parser.visitor import CodeVisitor
from codebase.helpers import (
    compute_package_full_path,
    visualize_graph,
    dump_graph_to_neo4j,
    read_python_file,
    merge_graphs,
    build_project_graph,
)
from codebase.code_graph.graph import CodeGraph
from codebase.code_graph.models import GraphNode, NodeType, Metadata


# -------------------------------
# Test compute_package_full_path
# -------------------------------


def test_compute_package_full_path_non_init(tmp_path):
    # Create a temporary directory structure with a normal Python file.
    project_root = tmp_path / "project"
    project_root.mkdir()
    subdir = project_root / "subdir"
    subdir.mkdir()
    file_path = subdir / "file.py"
    file_path.write_text("print('Hello')")

    # For a non-__init__ file, the function should strip the extension.
    # Expected package path: "subdir.file"
    result = compute_package_full_path(str(file_path), str(project_root))
    assert result == "subdir.file"


def test_compute_package_full_path_init(tmp_path):
    # Create a temporary directory structure with an __init__.py file.
    project_root = tmp_path / "project"
    project_root.mkdir()
    package_dir = project_root / "package"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("# package init")

    # For __init__.py, the file is removed from the path.
    # Expected package path: "package"
    result = compute_package_full_path(str(init_file), str(project_root))
    assert result == "package"


# -------------------------------
# Test visualize_graph
# -------------------------------


def test_visualize_graph(monkeypatch):
    # Create a simple NetworkX DiGraph with one node and one self-edge.
    graph = nx.DiGraph()
    node_data = {
        "id": "node1",
        "name": "TestNode",
        "node_type": "module",
        "metadata": {
            "source_file": "dummy.py",
            "docstring": "Test docstring",
            "line_start": 1,
            "line_end": 2,
            "type_hint": None,
        },
    }
    graph.add_node("node1", data=node_data)
    graph.add_edge("node1", "node1", relationship="contains")

    # Patch plt.show() to prevent an actual plot from rendering during tests.
    monkeypatch.setattr(plt, "show", lambda: None)

    # Call the visualization function; it should run without errors.
    visualize_graph(graph)


# -------------------------------
# Test dump_graph_to_neo4j
# -------------------------------

# Create dummy classes to simulate the Neo4j driver behavior.


class DummySession:
    def __init__(self):
        self.runs = []

    def run(self, query, **kwargs):
        self.runs.append((query, kwargs))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class DummyDriver:
    def __init__(self):
        self.session_obj = DummySession()

    def session(self):
        return self.session_obj

    def close(self):
        pass


def dummy_driver(uri, auth):
    return DummyDriver()


def test_dump_graph_to_neo4j(monkeypatch):
    # Monkeypatch GraphDatabase.driver with our dummy driver.
    monkeypatch.setattr(GraphDatabase, "driver", dummy_driver)

    # Create a simple graph with one node and one edge.
    graph = nx.DiGraph()
    node_data = {
        "id": "node1",
        "name": "TestNode",
        "node_type": "module",
        "metadata": {
            "source_file": "dummy.py",
            "docstring": "Test docstring",
            "line_start": 1,
            "line_end": 2,
            "type_hint": None,
        },
    }
    graph.add_node("node1", data=node_data)
    graph.add_edge("node1", "node1", relationship="contains")

    # Call the dump_graph_to_neo4j function.
    # It will use our dummy driver, so no real database is required.
    dump_graph_to_neo4j(graph, uri="bolt://dummy", user="neo4j", password="test")

    # If no exceptions are raised, we consider the dump function to be working.
    # For a more detailed test, you could inspect the dummy driver's session.runs attribute.
    assert True


def test_visit_import_from(tmp_path: Path):
    """
    Creates a temporary package with the following structure:

        tmp_path/
            mypackage/
                __init__.py
                test_module.py
                utils/
                    __init__.py

    The test_module.py file contains a relative import:
        from .utils import helper_function

    The test verifies that the CodeVisitor processes the relative import
    by creating an imported module node and establishing an IMPORTS edge.
    """
    # Set up temporary package structure.
    pkg_dir = tmp_path / "mypackage"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")

    # Create a utils subpackage
    utils_dir = pkg_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").write_text("")

    # Write test_module.py with a relative import statement.
    test_module_path = pkg_dir / "test_module.py"
    source_code = "from .utils import helper_function\n"
    test_module_path.write_text(source_code)

    # Add tmp_path to sys.path to allow module discovery.
    original_sys_path = sys.path.copy()
    sys.path.insert(0, str(tmp_path))

    try:
        # Instantiate the CodeVisitor for the test module.
        visitor = CodeVisitor(str(test_module_path), source_code, str(tmp_path))
        tree = ast.parse(source_code)
        visitor.visit(tree)

        # Verify the main module node exists.
        main_module_id = visitor.module_id
        assert main_module_id in visitor.graph_nodes

        # Compute the expected imported module id.
        # In __init__ of CodeVisitor:
        #   compute_package_full_path(test_module_path, tmp_path) returns "mypackage.test_module"
        #   simple_name is "test_module" (from "test_module.py")
        #   Thus, main_module_id becomes "module:mypackage.test_module.test_module"
        #
        # In visit_ImportFrom, with node.level == 1 and node.module == "utils":
        #   package_parts = ["mypackage", "test_module", "test_module"]
        #   base = "mypackage.test_module"
        #   base_module = "mypackage.test_module.utils"
        #   For alias "helper_function", the full module name is:
        #       "mypackage.test_module.utils.helper_function"
        #   and its node id is "module:mypackage.test_module.utils.helper_function"
        expected_imported_module = "mypackage.test_module.utils.helper_function"
        expected_imported_module_id = f"module:{expected_imported_module}"

        # Check that the imported module node was created.
        assert (
            expected_imported_module_id in visitor.graph_nodes
        ), f"Expected node id {expected_imported_module_id} not found in graph nodes."

        # Verify that an IMPORTS edge exists from the main module node to the imported module node.
        main_node = visitor.graph_nodes[main_module_id]
        imports_edge_found = any(
            rel.edge_type.value == "imports" and rel.target_node_id == expected_imported_module_id
            for rel in main_node.relationships
        )
        assert imports_edge_found, "IMPORTS relationship from main module to imported module not found."

    finally:
        # Restore sys.path to its original state.
        sys.path[:] = original_sys_path


# -------------------------------
# Tests for read_python_file
# -------------------------------


def test_read_python_file_success(tmp_path):
    # Create a temporary Python file with some content.
    file = tmp_path / "test.py"
    content = "print('Hello World')"
    file.write_text(content)

    # read_python_file should return the same content.
    result = read_python_file(file)
    assert result == content


def test_read_python_file_failure(tmp_path, monkeypatch):
    # Create a temporary file and simulate a read error by monkeypatching read_text.
    file = tmp_path / "test.py"
    file.write_text("print('Hello')")

    def fake_read_text(encoding):
        raise Exception("Simulated read error")

    # Patch the read_text method on the PosixPath class instead of the instance.
    monkeypatch.setattr(file.__class__, "read_text", fake_read_text)

    result = read_python_file(file)
    assert result is None


# -------------------------------
# Test for merge_graphs
# -------------------------------


def test_merge_graphs(tmp_path):
    # Create a master CodeGraph and a module-level CodeGraph.
    master = CodeGraph()
    module_graph = CodeGraph()

    # Create a dummy node and add it to module_graph.
    node = GraphNode(
        id="function:dummy.test_func",
        name="test_func",
        node_type=NodeType.FUNCTION,
        metadata=Metadata(source_file="dummy.py"),
    )
    module_graph.add_node(node)

    # Manually add an edge in module_graph (e.g., a self-call edge for simplicity).
    module_graph.graph.add_edge(node.id, node.id, relationship="calls")

    # Ensure master does not contain the node before merging.
    assert node.id not in master.get_networkx_graph().nodes

    # Merge the module_graph into the master graph.
    merge_graphs(master, module_graph)
    master_graph = master.get_networkx_graph()

    # Verify that the node and the edge have been merged.
    assert node.id in master_graph.nodes
    assert master_graph.has_edge(node.id, node.id)
    assert master_graph[node.id][node.id]["relationship"] == "calls"


# -------------------------------
# Test for build_project_graph
# -------------------------------


def test_build_project_graph(tmp_path):
    # Create two temporary Python files in the project directory.
    file_a = tmp_path / "a.py"
    code_a = "'''Module A docstring'''\n" "def func_a():\n" "    pass\n"
    file_a.write_text(code_a)

    file_b = tmp_path / "b.py"
    code_b = "'''Module B docstring'''\n" "class ClassB:\n" "    pass\n"
    file_b.write_text(code_b)

    # Build the project graph using the temporary project directory.
    cg = build_project_graph(str(tmp_path))
    graph = cg.get_networkx_graph()

    # For a file "a.py" in the root of the project, the computed package full path is "a"
    # and simple name is "a", so the module node id becomes "module:a.a".
    module_a_id = "module:a.a"
    # Similarly, for "b.py", the module id becomes "module:b.b".
    module_b_id = "module:b.b"

    # Verify that both module nodes exist in the graph.
    assert module_a_id in graph.nodes, f"Expected module node {module_a_id} not found in graph."
    assert module_b_id in graph.nodes, f"Expected module node {module_b_id} not found in graph."
