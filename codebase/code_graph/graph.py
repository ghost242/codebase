import networkx as nx
from typing import List, Dict, Any

from codebase.code_graph.models import GraphNode, GraphEdge


class CodeGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, node: GraphNode) -> None:
        """Adds a node to the NetworkX graph."""
        node_data = node.model_dump(exclude_none=True)
        node_data["node_type"] = node.node_type.value

        for rel in node_data.get("relationships", []):
            rel["edge_type"] = rel["edge_type"].value

        self.graph.add_node(node.id, data=node_data)

    def add_edge(self, source_id: str, edge: GraphEdge) -> None:
        """Adds an edge between two nodes in the graph."""
        self.graph.add_edge(source_id, edge.target_node_id, relationship=edge.edge_type.value)

    def build_from_nodes(self, nodes: List[GraphNode]) -> None:
        """Builds a graph structure from a list of GraphNodes."""
        for node in nodes:
            self.add_node(node)
        for node in nodes:
            for edge in node.relationships:
                self.add_edge(node.id, edge)

    def get_networkx_graph(self) -> nx.DiGraph:
        """Returns the NetworkX DiGraph representation."""
        return self.graph

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the graph to a dictionary format."""
        return nx.node_link_data(self.graph)

    def merge_nodes_by_reference(self) -> None:
        """Merges nodes that reference the same entity in the graph."""
        simple_to_ids: Dict[str, List[str]] = {}

        # Group nodes by simple name
        for node_id, attr in self.graph.nodes(data=True):
            name = attr.get("data", {}).get("name")
            if name:
                simple_to_ids.setdefault(name, []).append(node_id)

        # Merge nodes based on reference similarity
        for name, ids in simple_to_ids.items():
            if len(ids) <= 1:
                continue

            def score(nid: str):
                data = self.graph.nodes[nid]["data"]
                has_source_file = 1 if data.get("metadata", {}).get("source_file") else 0
                pkg = nid.split(":", 1)[1]  # Extract package path
                return (-has_source_file, pkg)

            canonical = min(ids, key=score)
            print(f"[merge_nodes_by_reference] Canonical for '{name}': {canonical}")

            # Redirect edges and remove redundant nodes
            for nid in ids:
                if nid == canonical:
                    continue

                if nid not in self.graph:
                    print(f"[merge_nodes_by_reference] Skipping '{nid}', as it does not exist in the graph.")
                    continue

                edges_to_add = []
                edges_to_remove = []

                for u, v, d in list(self.graph.edges(data=True)):
                    if v == nid and self.graph.has_node(u):
                        if not self.graph.has_edge(u, canonical):
                            edges_to_add.append((u, canonical, d))
                        edges_to_remove.append((u, v))
                    if u == nid and self.graph.has_node(v):
                        if not self.graph.has_edge(canonical, v):
                            edges_to_add.append((canonical, v, d))
                        edges_to_remove.append((u, v))

                for u, v, d in edges_to_add:
                    self.graph.add_edge(u, v, **d)
                for u, v in edges_to_remove:
                    if self.graph.has_edge(u, v):
                        self.graph.remove_edge(u, v)
                if self.graph.has_node(nid):
                    self.graph.remove_node(nid)
