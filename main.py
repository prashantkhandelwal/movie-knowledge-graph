import os

from dotenv import load_dotenv

from neo4j_client import Neo4jClient
from graph_rag import GraphRAG

load_dotenv()

db = Neo4jClient(
    os.getenv("NEO4J_URI"),
    os.getenv("NEO4J_USERNAME"),
    os.getenv("NEO4J_PASSWORD"),
    os.getenv("NEO4J_DATABASE"),
)

rag = GraphRAG(db)

print("GraphRAG started.")

while True:

    question = input(
        "\nQuestion > "
    )

    if question.lower() in [
        "quit",
        "exit"
    ]:
        break

    try:

        result = rag.ask(
            question
        )

        print("\nGenerated Cypher")
        print("=" * 50)
        print(result["cypher"])

        print("\nAnswer")
        print("=" * 50)
        print(result["answer"])

    except Exception as e:

        print(
            f"\nError: {e}"
        )

db.close()