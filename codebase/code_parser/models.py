from enum import StrEnum
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums for NodeType and EdgeType
# ---------------------------------------------------------------------------

class NodeType(StrEnum):
    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"
    DECORATOR = "decorator"


class EdgeType(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    INHERITS = "inherits"
    COMPOSES = "composes"
    CALLS = "calls"
    REFERENCES = "references"
    DECORATES = "decorates"


# ---------------------------------------------------------------------------
# Validation Rules for Correct Edge Directions
# ---------------------------------------------------------------------------

VALID_EDGES: Dict[EdgeType, List[Tuple[NodeType, NodeType]]] = {
    EdgeType.CONTAINS: [
        (NodeType.PACKAGE, NodeType.MODULE),
        (NodeType.MODULE, NodeType.CLASS),
        (NodeType.MODULE, NodeType.FUNCTION),
        (NodeType.CLASS, NodeType.CLASS),  # ✅ Allow classes to contain classes (nested classes)
        (NodeType.CLASS, NodeType.FUNCTION),
        (NodeType.CLASS, NodeType.VARIABLE),
        (NodeType.CLASS, NodeType.DECORATOR),
        (NodeType.FUNCTION, NodeType.FUNCTION),  # ✅ Allow functions to contain functions (nested functions)
        (NodeType.FUNCTION, NodeType.CLASS),  # ✅ Allow functions to contain classes (nested classes)
    ],
    EdgeType.IMPORTS: [
        (NodeType.MODULE, NodeType.MODULE),
        (NodeType.PACKAGE, NodeType.PACKAGE),
    ],
    EdgeType.INHERITS: [
        (NodeType.CLASS, NodeType.CLASS),
    ],
    EdgeType.COMPOSES: [
        (NodeType.CLASS, NodeType.CLASS),
        (NodeType.CLASS, NodeType.FUNCTION),
        (NodeType.CLASS, NodeType.VARIABLE),
    ],
    EdgeType.CALLS: [
        (NodeType.FUNCTION, NodeType.FUNCTION),
    ],
    EdgeType.REFERENCES: [
        (NodeType.FUNCTION, NodeType.VARIABLE),
        (NodeType.CLASS, NodeType.VARIABLE),
    ],
    EdgeType.DECORATES: [
        (NodeType.DECORATOR, NodeType.FUNCTION),
        (NodeType.DECORATOR, NodeType.CLASS),
    ],
}



# ---------------------------------------------------------------------------
# Metadata Model
# ---------------------------------------------------------------------------

class Metadata(BaseModel):
    source_file: Optional[str] = Field(default=None, description="The source file path.")
    line_start: Optional[int] = Field(default=None, description="Start line number.")
    line_end: Optional[int] = Field(default=None, description="End line number.")
    docstring: Optional[str] = Field(default=None, description="Docstring of the element.")
    type_hint: Optional[str] = Field(default=None, description="Type hint if any.")
    additional: Optional[Dict[str, Any]] = Field(default=None, description="Any extra metadata.")


# ---------------------------------------------------------------------------
# GraphEdge Model with Validation
# ---------------------------------------------------------------------------

class GraphEdge(BaseModel):
    edge_type: EdgeType = Field(..., description="Type of relationship edge.")
    source_node_id: str = Field(..., description="Composite id of the source node.")
    target_node_id: str = Field(..., description="Composite id of the target node.")
    source_node_type: NodeType = Field(..., description="Type of the source node.")
    target_node_type: NodeType = Field(..., description="Type of the target node.")

    @classmethod
    def validate_edge(cls, edge_type: EdgeType, source_type: NodeType, target_type: NodeType):
        """ Ensure the edge is valid according to predefined direction rules. """
        if (source_type, target_type) not in VALID_EDGES.get(edge_type, []):
            raise ValueError(f"Invalid edge direction: {source_type} --({edge_type})--> {target_type}")

    def __init__(self, **data):
        """ Custom constructor to enforce edge validation. """
        super().__init__(**data)
        self.validate_edge(self.edge_type, self.source_node_type, self.target_node_type)


# ---------------------------------------------------------------------------
# GraphNode Model
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str = Field(..., description="Composite id: 'node_type:package_full_path.name'.")
    name: str = Field(..., description="Simple name of the node.")
    node_type: NodeType = Field(..., description="Type of node (module, class, etc.).")
    metadata: Optional[Metadata] = Field(default=None, description="Optional node metadata.")
    relationships: List[GraphEdge] = Field(default_factory=list, description="List of relationship edges.")

    def add_relationship(self, edge: GraphEdge):
        """ Ensure relationships only contain valid edges. """
        if edge.source_node_id != self.id:
            raise ValueError("The source node ID must match the current node's ID.")
        self.relationships.append(edge)


# ---------------------------------------------------------------------------
# Example Usage & Testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        # Creating a valid inheritance edge
        edge = GraphEdge(
            edge_type=EdgeType.INHERITS,
            source_node_id="class:example.ParentClass",
            target_node_id="class:example.ChildClass",
            source_node_type=NodeType.CLASS,
            target_node_type=NodeType.CLASS,
        )
        print("✅ Valid Edge Created:", edge)

        # Trying to create an invalid edge (e.g., FUNCTION inheriting from CLASS)
        invalid_edge = GraphEdge(
            edge_type=EdgeType.INHERITS,
            source_node_id="function:example.func",
            target_node_id="class:example.MyClass",
            source_node_type=NodeType.FUNCTION,
            target_node_type=NodeType.CLASS,
        )
    except ValidationError as e:
        print("❌ Validation Error:", e)

    # Create a node and add a valid relationship
    node = GraphNode(
        id="class:example.ParentClass",
        name="ParentClass",
        node_type=NodeType.CLASS,
        relationships=[]
    )

    try:
        node.add_relationship(edge)
        print("✅ Relationship added successfully.")
    except ValueError as e:
        print("❌ Relationship Error:", e)
