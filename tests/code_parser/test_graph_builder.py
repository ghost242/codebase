from codebase.code_parser.graph_builder import (
    read_python_file,
    merge_graphs,
    build_project_graph,
)
from codebase.code_parser.code_graph import CodeGraph
from codebase.code_parser.models import GraphNode, NodeType, Metadata

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

    from codebase.code_parser.graph_builder import read_python_file

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
