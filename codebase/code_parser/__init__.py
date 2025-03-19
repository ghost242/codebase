from codebase.code_parser.graph_builder import build_project_graph

def process_files(project_directory):
    # Set the root directory of your package project here.
    project_graph = build_project_graph(project_directory)
    project_graph.dump_to_neo4j(
        uri="bolt://localhost:7687", user="neo4j", password="devpassword"
    )
