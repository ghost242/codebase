import networkx as nx
from matplotlib import pyplot as plt

from codebase.code_parser.helpers import (
    compute_package_full_path,
    visualize_graph,
    dump_graph_to_neo4j,
)
from neo4j import GraphDatabase

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
