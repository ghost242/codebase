from codebase.code_graph.utils import build_project_graph, dump_graph_to_neo4j

if __name__ == "__main__":
    import sys
    # Define one or more project directories.
    project_directories: list[str] = [
        "/Users/jeffrey/Playground/fastapi_family/.venv/lib/python3.11/site-packages",
    ]
    # Ensure the directories are on sys.path.
    sys.path.append("/Users/jeffrey/Playground/fastapi_family/.venv/lib/python3.11/site-packages")
    project_graph = build_project_graph(project_directories[0])
    project_graph.merge_nodes_by_reference()

    dump_graph_to_neo4j(
        graph=project_graph.get_networkx_graph(),
        uri="bolt://127.0.0.1:7687",
        user="neo4j",
        password="devpassword",
        cleanup=True,
    )
