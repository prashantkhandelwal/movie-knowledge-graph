"""Create and populate a Neo4j movie database from the data folder.

Usage:
	uv run python import/import.py --uri bolt://localhost:7687 --user neo4j \
		--password secret --batch-size 1000

Connection settings may also be supplied with NEO4J_URI, NEO4J_USER,
NEO4J_PASSWORD, and NEO4J_DATABASE. Re-running the script is safe: nodes and
relationships are merged using stable source identifiers.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import ijson
from neo4j import GraphDatabase


LOGGER = logging.getLogger("movie_import")
DEFAULT_DATABASE = "moviekg"
DATASET_ORDER = (
	"moviedb.movies.json",
	"moviedb.person.json",
	"moviedb.credits.json",
)
GENDERS = {
	0: "Not specified",
	1: "Female",
	2: "Male",
	3: "Non-binary",
}
CREW_RELATIONSHIPS = {
	"Art": "DESIGNED_ART",
	"Camera": "OPERATED_CAMERA",
	"Costume & Make-Up": "DESIGNED_COSTUME",
	"Directing": "DIRECTED",
	"Editing": "EDITED",
	"Lighting": "SET_LIGHTING",
	"Production": "PRODUCED",
	"Sound": "WORKED_ON_SOUND",
	"Visual Effects": "CREATED_VFX",
	"Writing": "WROTE",
	"Crew": "WORKED_AS_CREW",
}
CREDIT_PROPERTY_NAMES = (
	"popularity",
	"character",
	"order",
	"credit_id",
	"cast_id",
	"job",
	"department",
)


def database_identifier(value: str) -> str:
	if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", value):
		raise ValueError(f"Invalid Neo4j database name: {value!r}")
	return value


def normalize_scalar(value: Any) -> Any:
	if not isinstance(value, dict):
		return value
	if len(value) != 1:
		raise ValueError(f"Cannot store object as a Neo4j property: {value!r}")

	key, encoded = next(iter(value.items()))
	if key in {"$numberInt", "$numberLong"}:
		return int(encoded)
	if key in {"$numberDouble", "$numberDecimal"}:
		return float(encoded)
	raise ValueError(f"Unsupported Extended JSON property value: {value!r}")


def clean_properties(properties: dict[str, Any]) -> dict[str, Any]:
	return {
		name: normalize_scalar(value)
		for name, value in properties.items()
		if value is not None
	}


def parse_datetime(value: Any) -> datetime | None:
	if not isinstance(value, dict):
		return None
	date_value = value.get("$date")
	if isinstance(date_value, str):
		return datetime.fromisoformat(date_value.replace("Z", "+00:00"))
	if isinstance(date_value, dict):
		milliseconds = normalize_scalar(date_value)
		if not isinstance(milliseconds, (int, float)):
			raise ValueError(f"Invalid Extended JSON date value: {value!r}")
		return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
			milliseconds=milliseconds
		)
	if date_value is not None:
		return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
			milliseconds=normalize_scalar(date_value)
		)
	return None


def person_properties(record: dict[str, Any]) -> dict[str, Any]:
	gender = normalize_scalar(record.get("gender"))
	also_known_as = record.get("also_known_as")
	if also_known_as is not None and not isinstance(also_known_as, list):
		raise ValueError(f"Invalid person also_known_as value: {also_known_as!r}")
	mongo_id = record.get("_id")
	if mongo_id is not None:
		if not isinstance(mongo_id, dict) or not isinstance(mongo_id.get("$oid"), str):
			raise ValueError(f"Invalid person _id value: {mongo_id!r}")
		mongo_id = mongo_id["$oid"]

	external_links = record.get("external_links")
	if external_links is None:
		external_links = {}
	if not isinstance(external_links, dict):
		raise ValueError(f"Invalid person external_links value: {external_links!r}")

	properties = clean_properties(
		{
			"id": record.get("id"),
			"mongo_id": mongo_id,
			"adult": record.get("adult"),
			"also_known_as": [
				normalize_scalar(name)
				for name in also_known_as
				if name is not None
			] if also_known_as is not None else None,
			"biography": record.get("biography"),
			"birthday": record.get("birthday"),
			"deathday": record.get("deathday"),
			"gender": GENDERS.get(gender, str(gender) if gender is not None else None),
			"homepage": record.get("homepage"),
			"imdb_id": record.get("imdb_id"),
			"known_for_department": record.get("known_for_department"),
			"name": record.get("name"),
			"original_name": record.get("original_name", record.get("name")),
			"place_of_birth": record.get("place_of_birth"),
			"popularity": record.get("popularity"),
			"profile_path": record.get("profile_path"),
		}
	)
	properties.update(
		clean_properties(
			{
				f"external_links_{name}": value
				for name, value in external_links.items()
			}
		)
	)
	return properties


def movie_row(record: dict[str, Any]) -> dict[str, Any]:
	movie_id = normalize_scalar(record.get("id"))
	if movie_id is None:
		raise ValueError("Movie record is missing id")

	countries = {
		country.get("iso_3166_1"): country.get("name")
		for country in record.get("production_countries", [])
		if isinstance(country, dict)
	}
	companies = []
	for company in record.get("production_companies", []):
		if not isinstance(company, dict) or company.get("id") is None:
			continue
		country_code = company.get("origin_country")
		companies.append(
			clean_properties(
				{
					"id": company["id"],
					"name": company.get("name"),
					"country_code": country_code,
					"country_name": countries.get(country_code),
				}
			)
		)

	return {
		"id": movie_id,
		"properties": clean_properties(
			{
				"id": movie_id,
				"title": record.get("title"),
				"isadult": record.get("adult"),
				"budget": record.get("budget"),
				"imdbid": record.get("imdb_id"),
				"revenue": record.get("revenue"),
				"runtime": record.get("runtime"),
				"status": record.get("status"),
				"originallanguage": record.get("original_language"),
				"originaltitle": record.get("original_title"),
				"releasedate": parse_datetime(record.get("release_date")),
				"video": record.get("video"),
				"voteaverage": record.get("vote_average"),
				"votecount": record.get("vote_count"),
			}
		),
		"genres": [
			clean_properties({"id": genre.get("id"), "name": genre.get("name")})
			for genre in record.get("genres", [])
			if isinstance(genre, dict) and genre.get("id") is not None
		],
		"companies": companies,
		"languages": [
			clean_properties(
				{
					"code": language.get("iso_639_1"),
					"name": language.get("english_name", language.get("name")),
				}
			)
			for language in record.get("spoken_languages", [])
			if isinstance(language, dict) and language.get("iso_639_1")
		],
	}


def iter_json_array(json_file: Path) -> Iterator[dict[str, Any]]:
	with json_file.open("rb") as stream:
		for index, record in enumerate(ijson.items(stream, "item", use_float=True)):
			if not isinstance(record, dict):
				raise ValueError(f"{json_file} record {index} is not an object")
			yield record


class JsonGraphImporter:
	def __init__(self, driver: Any, database: str, batch_size: int) -> None:
		self.driver = driver
		self.database = database_identifier(database)
		self.batch_size = batch_size
		self.node_count = 0
		self.relationship_count = 0
		self.skipped_relationship_count = 0

	def create_database(self) -> None:
		LOGGER.info("Creating or starting database %s", self.database)
		with self.driver.session(database="system") as session:
			session.run(
				f"CREATE DATABASE `{self.database}` IF NOT EXISTS"
			).consume()
			session.run(f"START DATABASE `{self.database}` WAIT").consume()
		LOGGER.info("Database %s is online", self.database)

	def create_constraints(self) -> None:
		constraints = (
			("movie_id", "Movie", "id"),
			("person_id", "Person", "id"),
			("genre_id", "Genre", "id"),
			("company_id", "Company", "id"),
			("language_code", "Language", "code"),
		)
		with self.driver.session(database=self.database) as session:
			for name, label, property_name in constraints:
				LOGGER.debug(
					"Ensuring constraint %s on %s.%s",
					name,
					label,
					property_name,
				)
				session.run(
					f"CREATE CONSTRAINT {name} IF NOT EXISTS "
					f"FOR (n:`{label}`) REQUIRE n.`{property_name}` IS UNIQUE"
				).consume()
		LOGGER.info("Verified %d uniqueness constraints", len(constraints))

	def _write_batches(
		self,
		records: Iterator[dict[str, Any]],
		writer: Callable[[Any, list[dict[str, Any]]], None],
		record_type: str,
	) -> None:
		batch: list[dict[str, Any]] = []
		batch_number = 0
		processed = 0
		with self.driver.session(database=self.database) as session:
			for record in records:
				batch.append(record)
				if len(batch) == self.batch_size:
					writer(session, batch)
					batch_number += 1
					processed += len(batch)
					LOGGER.info(
						"Processed %s batch %d: %d records (%d total)",
						record_type,
						batch_number,
						len(batch),
						processed,
					)
					batch = []
			if batch:
				writer(session, batch)
				batch_number += 1
				processed += len(batch)
				LOGGER.info(
					"Processed %s batch %d: %d records (%d total)",
					record_type,
					batch_number,
					len(batch),
					processed,
				)

	def import_movies(self, json_file: Path) -> None:
		query = """
		UNWIND $rows AS row
		MERGE (movie:Movie {id: row.id})
		SET movie += row.properties
		FOREACH (genre IN row.genres |
			MERGE (genre_node:Genre {id: genre.id})
			SET genre_node += genre
			MERGE (movie)-[:HAS_GENRE]->(genre_node)
		)
		FOREACH (company IN row.companies |
			MERGE (company_node:Company {id: company.id})
			SET company_node += company
			MERGE (movie)-[:PRODUCED_BY]->(company_node)
		)
		FOREACH (language IN row.languages |
			MERGE (language_node:Language {code: language.code})
			SET language_node += language
			MERGE (movie)-[:SPOKEN_IN]->(language_node)
		)
		"""

		def write(session: Any, rows: list[dict[str, Any]]) -> None:
			session.run(query, rows=rows).consume()
			self.node_count += len(rows)
			self.relationship_count += sum(
				len(row["genres"]) + len(row["companies"]) + len(row["languages"])
				for row in rows
			)

		self._write_batches(
			(movie_row(record) for record in iter_json_array(json_file)),
			write,
			"movie",
		)

	def import_people(self, json_file: Path) -> None:
		query = """
		UNWIND $rows AS properties
		MERGE (person:Person {id: properties.id})
		SET person += properties
		"""

		def records() -> Iterator[dict[str, Any]]:
			for index, record in enumerate(iter_json_array(json_file)):
				properties = person_properties(record)
				if properties.get("id") is None:
					raise ValueError(f"{json_file} record {index} is missing id")
				yield properties

		def write(session: Any, rows: list[dict[str, Any]]) -> None:
			session.run(query, rows=rows).consume()
			self.node_count += len(rows)

		self._write_batches(records(), write, "person")

	def _write_credits(
		self,
		session: Any,
		relationship: str,
		rows: list[dict[str, Any]],
	) -> None:
		query = f"""
		UNWIND $rows AS row
		MATCH (movie:Movie {{id: row.movie_id}})
		MERGE (person:Person {{id: row.person.id}})
		SET person += row.person
		MERGE (person)-[credit:`{relationship}` {{credit_id: row.credit_id}}]->(movie)
		SET credit += row.properties
		RETURN count(*) AS processed,
			collect(DISTINCT row.movie_id) AS matched_movie_ids
		"""
		result = session.run(query, rows=rows).single(strict=True)
		processed = result["processed"]
		if processed != len(rows):
			matched_movie_ids = set(result["matched_movie_ids"])
			missing_movie_ids = sorted(
				{
					row["movie_id"]
					for row in rows
					if row["movie_id"] not in matched_movie_ids
				},
				key=str,
			)
			skipped = len(rows) - processed
			self.skipped_relationship_count += skipped
			LOGGER.warning(
				"Skipped %d %s credits because %d referenced movies were not "
				"imported (sample movie IDs: %s)",
				skipped,
				relationship,
				len(missing_movie_ids),
				", ".join(str(movie_id) for movie_id in missing_movie_ids[:10]),
			)
		self.relationship_count += processed
		LOGGER.info(
			"Processed %s relationship batch: %d records "
			"(%d total relationships)",
			relationship,
			processed,
			self.relationship_count,
		)

	def import_credits(self, json_file: Path) -> None:
		buffers: dict[str, list[dict[str, Any]]] = {
			relationship: []
			for relationship in {"ACTED_IN", *CREW_RELATIONSHIPS.values()}
		}

		def flush(session: Any, relationship: str) -> None:
			rows = buffers[relationship]
			if rows:
				self._write_credits(session, relationship, rows)
				buffers[relationship] = []

		with self.driver.session(database=self.database) as session:
			for record_index, record in enumerate(iter_json_array(json_file)):
				movie_id = normalize_scalar(record.get("id"))
				if movie_id is None:
					raise ValueError(f"{json_file} record {record_index} is missing id")

				credits = [
					("ACTED_IN", credit)
					for credit in record.get("cast", [])
					if isinstance(credit, dict)
				]
				credits.extend(
					(
						CREW_RELATIONSHIPS.get(
							credit.get("department"), "WORKED_AS_CREW"
						),
						credit,
					)
					for credit in record.get("crew", [])
					if isinstance(credit, dict)
				)

				for relationship, credit in credits:
					credit_id = normalize_scalar(credit.get("credit_id"))
					person_id = normalize_scalar(credit.get("id"))
					if credit_id is None or person_id is None:
						raise ValueError(
							f"{json_file} record {record_index} has a credit "
							"without credit_id or person id"
						)
					buffers[relationship].append(
						{
							"movie_id": movie_id,
							"credit_id": credit_id,
							"person": person_properties(credit),
							"properties": clean_properties(
								{
									name: credit.get(name)
									for name in CREDIT_PROPERTY_NAMES
								}
							),
						}
					)
					if len(buffers[relationship]) >= self.batch_size:
						flush(session, relationship)

			for relationship in buffers:
				flush(session, relationship)

	def import_data(self, data_folder: Path) -> None:
		handlers = {
			"moviedb.movies.json": self.import_movies,
			"moviedb.person.json": self.import_people,
			"moviedb.credits.json": self.import_credits,
		}
		for filename in DATASET_ORDER:
			json_file = data_folder / filename
			if not json_file.is_file():
				raise FileNotFoundError(f"Required data file does not exist: {json_file}")
			started_at = perf_counter()
			start_nodes = self.node_count
			start_relationships = self.relationship_count
			LOGGER.info(
				"Importing %s (%.1f MiB)",
				filename,
				json_file.stat().st_size / (1024 * 1024),
			)
			handlers[filename](json_file)
			LOGGER.info(
				"Completed %s in %.1f seconds: %d node records and "
				"%d relationship records",
				filename,
				perf_counter() - started_at,
				self.node_count - start_nodes,
				self.relationship_count - start_relationships,
			)


def find_data_folder(explicit: str | None) -> Path:
	if explicit:
		folder = Path(explicit).resolve()
		if folder.is_dir():
			return folder
		raise FileNotFoundError(f"Data folder does not exist: {folder}")

	script = Path(__file__).resolve()
	for folder in (script.parent.parent / "data", script.parent / "data"):
		if folder.is_dir():
			return folder
	raise FileNotFoundError("Could not find the data folder")


def positive_integer(value: str) -> int:
	number = int(value)
	if number <= 0:
		raise argparse.ArgumentTypeError("must be greater than zero")
	return number


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Import movie JSON data into Neo4j using batched writes"
	)
	parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
	parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
	parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
	parser.add_argument(
		"--database",
		default=os.getenv("NEO4J_DATABASE", DEFAULT_DATABASE),
	)
	parser.add_argument(
		"--batch-size",
		type=positive_integer,
		default=1000,
		help="Number of nodes or relationships written per transaction (default: 1000)",
	)
	parser.add_argument(
		"--log-level",
		choices=("DEBUG", "INFO", "WARNING", "ERROR"),
		default=os.getenv("LOG_LEVEL", "INFO").upper(),
		help="Logging verbosity (default: INFO)",
	)
	parser.add_argument("--data", help="Path to the data folder")
	args = parser.parse_args()
	if not args.password:
		parser.error("provide --password or set NEO4J_PASSWORD")

	logging.basicConfig(
		level=getattr(logging, args.log_level),
		format="%(asctime)s %(levelname)s %(message)s",
	)
	data_folder = find_data_folder(args.data)
	with GraphDatabase.driver(args.uri, auth=(args.user, args.password)) as driver:
		driver.verify_connectivity()
		LOGGER.info("Connected to %s", args.uri)
		importer = JsonGraphImporter(driver, args.database, args.batch_size)
		importer.create_database()
		importer.create_constraints()
		importer.import_data(data_folder)
		LOGGER.info(
			"Import complete for %s: %d node records and "
			"%d relationship records processed; %d orphan relationships skipped",
			importer.database,
			importer.node_count,
			importer.relationship_count,
			importer.skipped_relationship_count,
		)


if __name__ == "__main__":
	main()
