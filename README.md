# Code Graph Builder

The **Code Graph Builder** is a Python-based tool designed to parse a codebase and represent its structure as a graph. It leverages Python's abstract syntax tree (AST) to analyze source files and builds a graph where each node represents a code element (module, class, function, etc.) and edges represent relationships (e.g., contains, imports, calls, etc.). This graph-based representation can be used for visualization, analysis, or integration with graph databases like Neo4j.

## Features

- **AST-Based Parsing:** Uses Python's `ast` module to traverse and analyze code structure.
- **Graph Modeling:** Represents code elements using well-defined models and relationship rules.
- **Validation:** Utilizes [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation to ensure correct relationships.
- **Visualization:** Integrates with [NetworkX](https://networkx.org/) and [Matplotlib](https://matplotlib.org/) for graph visualization.
- **Database Integration:** Supports dumping the graph into a Neo4j database via the official [neo4j Python driver](https://neo4j.com/developer/python/).
- **Modular Design:** Separates functionality into clear modules:
  - **Models:** Defines graph models (`GraphNode`, `GraphEdge`, etc.) and valid edge relationships.
  - **Helpers:** Provides utility functions for package path computation, graph visualization, and database export.
  - **Graph Builder:** Reads Python files, merges module-level graphs, and builds a project-wide code graph.
  - **Code Visitor:** Implements an AST visitor that extracts code structure and builds nodes and edges.
  - **Code Graph:** Constructs the NetworkX graph from the extracted nodes and offers additional functionality (serialization, node merging, etc.).

## Project Structure

- **models.py:**  
  Contains the Pydantic models for nodes and edges, as well as enums for node types and edge types. It also enforces validation rules for relationships.

- **helpers.py:**  
  Implements utility functions:

  - `compute_package_full_path`: Converts a file path into a dotted package path.
  - `visualize_graph`: Visualizes a NetworkX graph using Matplotlib.
  - `dump_graph_to_neo4j`: Exports the graph to a Neo4j database.

- **graph_builder.py:**  
  Provides functions to:

  - Read Python files from a directory.
  - Merge module-level graphs into a master project graph.
  - Build a complete code graph for the project.

- **code_visitor.py:**  
  Defines a custom AST node visitor that:
  - Parses Python source code.
  - Creates nodes for modules, classes, and functions.
  - Establishes relationships like "contains", "imports", and "calls" among nodes.
- **code_graph.py:**  
  Uses the data gathered by the `CodeVisitor` to build a NetworkX graph. It includes methods for:

  - Adding nodes and edges.
  - Serializing the graph.
  - Visualizing the graph.
  - Merging nodes by reference to resolve duplicates.
  - Dumping the graph to Neo4j.

- ****init**.py:**  
  Exposes the `build_project_graph` function as the primary interface to generate a graph representation from a project directory.

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/yourusername/code-graph-builder.git
   cd code-graph-builder
   ```

2. **Create and activate a virtual environment (optional but recommended):**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install the required dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   _Dependencies include:_

   - Python 3.8+
   - `networkx`
   - `matplotlib`
   - `pydantic`
   - `neo4j`

## Usage

To build a code graph for your project, you can use the provided function in the package's `__init__.py`. For example:

```python
from codebase.code_parser import build_project_graph

project_directory = "/path/to/your/project"
project_graph = build_project_graph(project_directory)

# Visualize the graph
project_graph.visualize()

# Optionally, dump the graph to a Neo4j database
project_graph.dump_to_neo4j(uri="bolt://localhost:7687", user="neo4j", password="yourpassword")
```

## Testing

The project uses [pytest](https://docs.pytest.org/) for unit testing. To run the tests, execute:

```bash
pytest
```

The tests cover all major modules, including AST parsing, graph construction, and utility functions.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any features, bug fixes, or enhancements.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
