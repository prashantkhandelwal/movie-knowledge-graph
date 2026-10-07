# Movie Knowledge Graph

A local GraphRAG application that imports movie metadata into Neo4j and uses
Ollama to translate natural-language questions into Cypher queries.

## Features

- Streams large JSON datasets with `ijson` instead of loading them fully into
  memory.
- Imports movies, people, cast, crew, genres, production companies, and spoken
  languages in configurable batches.
- Safely supports repeated imports by merging nodes and relationships using
  stable source identifiers.
- Creates Neo4j uniqueness constraints for imported entities.
- Generates schema-aware Cypher with a local Ollama model.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Neo4j with permission to create and start databases
- [Ollama](https://ollama.com/)

## Setup

Install the Python dependencies:

```shell
uv sync
```

Pull the model used by the application:

```shell
ollama pull qwen2.5-coder:7b
```

Copy `.env.example` to `.env` and update the Neo4j connection settings:

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=moviekg
```

The Neo4j database name used by the application must match the database used
during import.

## Import the dataset

The importer expects these files in `data/`:

- `moviedb.movies.json`
- `moviedb.person.json`
- `moviedb.credits.json`

Run the importer with:

```shell
uv run python import/import.py --password password
```

By default, it connects to `bolt://localhost:7687` as `neo4j`, creates or
starts the `moviekg` database, and writes records in batches of 1,000.

All importer options:

```text
--uri URI              Neo4j Bolt URI
--user USER            Neo4j username
--password PASSWORD    Neo4j password (required unless NEO4J_PASSWORD is set)
--database DATABASE    Database to create and populate (default: moviekg)
--batch-size SIZE      Records written per transaction (default: 1000)
--log-level LEVEL      DEBUG, INFO, WARNING, or ERROR
--data PATH            Directory containing the required JSON files
```

Connection values can also be supplied through `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, and `NEO4J_DATABASE`:

```shell
uv run python import/import.py
```

> The importer uses `NEO4J_USER`, while the interactive application uses
> `NEO4J_USERNAME`.

The import order is movies, people, then credits. Progress and skipped credit
relationships are reported in the logs. Re-running the command updates
existing entities without intentionally duplicating them.

### Import from another directory

```shell
uv run python import/import.py --data C:\path\to\data --password password
```

### Tune write batches

Use a smaller batch if Neo4j has limited memory, or a larger batch to reduce
transaction overhead:

```shell
uv run python import/import.py --password password --batch-size 500
```

## Run the application

Make sure Neo4j and Ollama are running, then start the interactive prompt:

```shell
uv run python main.py
```

Ask a movie-related question:

```text
Question > Which movies did Christopher Nolan direct?
```

The application prints the generated Cypher and the query result. Enter
`quit` or `exit` to stop.

## Graph model

The importer creates these node labels:

- `Movie`
- `Person`
- `Genre`
- `Company`
- `Language`

Movie metadata relationships:

```text
(Movie)-[:HAS_GENRE]->(Genre)
(Movie)-[:PRODUCED_BY]->(Company)
(Movie)-[:SPOKEN_IN]->(Language)
```

Cast and crew relationships point from a person to a movie:

```text
(Person)-[:ACTED_IN]->(Movie)
(Person)-[:DIRECTED]->(Movie)
(Person)-[:PRODUCED]->(Movie)
(Person)-[:WROTE]->(Movie)
(Person)-[:EDITED]->(Movie)
(Person)-[:OPERATED_CAMERA]->(Movie)
(Person)-[:SET_LIGHTING]->(Movie)
(Person)-[:WORKED_ON_SOUND]->(Movie)
(Person)-[:DESIGNED_COSTUME]->(Movie)
(Person)-[:DESIGNED_ART]->(Movie)
(Person)-[:CREATED_VFX]->(Movie)
(Person)-[:WORKED_AS_CREW]->(Movie)
```

Cast relationships include properties such as `character`, `order`, and
`credit_id`. Crew relationships include the exact `job`, `department`, and
`credit_id`.

## Project structure

```text
.
|-- data/               JSON datasets
|-- import/import.py    Batched Neo4j importer
|-- main.py             Interactive command-line application
|-- graph_rag.py        Natural language to Cypher workflow
|-- neo4j_client.py     Neo4j query client
|-- prompts.py          Graph schema and generation rules
`-- pyproject.toml      Python project and dependencies
```