from codebase.code_graph.graph import CodeGraph
from codebase.code_graph.models import GraphNode, GraphEdge, NodeType, EdgeType, Metadata


def create_test_node(node_id, name, source_file=None):
    """Helper to create a GraphNode with minimal attributes."""
    return GraphNode(id=node_id, name=name, node_type=NodeType.FUNCTION, metadata=Metadata(source_file=source_file))


def test_add_node_and_edge():
    """Test adding nodes and an edge to the CodeGraph."""
    cg = CodeGraph()
    # Create two nodes
    node1 = create_test_node("function:dummy.func1", "func1", "dummy.py")
    node2 = create_test_node("function:dummy.func2", "func2", "dummy.py")
    cg.add_node(node1)
    cg.add_node(node2)
    # Create an edge from node1 to node2 (simulate a function call)
    edge = GraphEdge(
        edge_type=EdgeType.CALLS,
        source_node_id=node1.id,
        target_node_id=node2.id,
        source_node_type=node1.node_type,
        target_node_type=node2.node_type,
    )
    cg.add_edge(node1.id, edge)

    graph = cg.get_networkx_graph()
    assert node1.id in graph.nodes
    assert node2.id in graph.nodes
    assert graph.has_edge(node1.id, node2.id)
    assert graph[node1.id][node2.id]["relationship"] == "calls"


def test_build_from_nodes():
    """Test building the networkx graph from a list of nodes."""
    cg = CodeGraph()
    node1 = create_test_node("function:dummy.func1", "func1", "dummy.py")
    node2 = create_test_node("function:dummy.func2", "func2", "dummy.py")
    # Manually add a relationship edge to node1
    edge = GraphEdge(
        edge_type=EdgeType.CALLS,
        source_node_id=node1.id,
        target_node_id=node2.id,
        source_node_type=node1.node_type,
        target_node_type=node2.node_type,
    )
    node1.relationships.append(edge)
    nodes = [node1, node2]

    cg.build_from_nodes(nodes)
    graph = cg.get_networkx_graph()
    assert node1.id in graph.nodes
    assert node2.id in graph.nodes
    assert graph.has_edge(node1.id, node2.id)
    assert graph[node1.id][node2.id]["relationship"] == "calls"


def test_build_from_code(tmp_path):
    """Test building a CodeGraph from actual code via CodeVisitor."""
    # Write a simple Python file with one function and one class.
    code = "def my_function():\n" "    pass\n\n" "class MyClass:\n" "    pass\n"
    source_file = tmp_path / "dummy.py"
    source_file.write_text(code)

    cg = CodeGraph()
    # build_from_code leverages CodeVisitor to parse the code.
    cg = cg.build_from_code(source_file=str(source_file), code=code, project_root=str(tmp_path))
    graph = cg.get_networkx_graph()

    # Expect the module node plus nodes for the function and class.
    module_node_id = "module:dummy.dummy"  # Computed based on file naming in CodeVisitor.
    function_node_id = "function:dummy.my_function"
    class_node_id = "class:dummy.MyClass"

    nodes = list(graph.nodes)
    assert module_node_id in nodes
    assert function_node_id in nodes
    assert class_node_id in nodes


def test_to_dict():
    """Test serialization of the CodeGraph to a dictionary."""
    cg = CodeGraph()
    node1 = create_test_node("function:dummy.func1", "func1", "dummy.py")
    cg.add_node(node1)
    d = cg.to_dict()
    # The serialized dict should include 'nodes' and 'links' (or 'edges' depending on version).
    assert "nodes" in d
    assert "links" in d or "edges" in d


def test_merge_nodes_by_reference():
    """Test that merge_nodes_by_reference merges nodes with the same simple name."""
    cg = CodeGraph()
    # Create two nodes with the same simple name "Test".
    node1 = create_test_node("function:dummy.Test", "Test", "dummy.py")  # Node with metadata.
    node2 = create_test_node("function:dummy_alt.Test", "Test", None)  # Node without metadata.

    # Add both nodes to the graph.
    cg.add_node(node1)
    cg.add_node(node2)

    # Create a third node that points to node2 via an edge.
    node3 = create_test_node("function:dummy.func", "func", "dummy.py")
    cg.add_node(node3)
    edge = GraphEdge(
        edge_type=EdgeType.CALLS,
        source_node_id=node3.id,
        target_node_id=node2.id,
        source_node_type=node3.node_type,
        target_node_type=node2.node_type,
    )
    cg.add_edge(node3.id, edge)

    # Verify both nodes exist before merging.
    graph = cg.get_networkx_graph()
    assert node1.id in graph.nodes
    assert node2.id in graph.nodes

    # Perform merge operation.
    cg.merge_nodes_by_reference()
    graph_after = cg.get_networkx_graph()

    # The canonical node should be node1 (which has metadata).
    assert node1.id in graph_after.nodes
    assert node2.id not in graph_after.nodes
    # The edge from node3 should now point to node1.
    assert graph_after.has_edge(node3.id, node1.id)
    # No edge should target the removed node2.
    for _, v in graph_after.edges():
        assert v != node2.id
