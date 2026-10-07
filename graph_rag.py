import json
from collections.abc import Mapping

from ollama import chat

from prompts import SCHEMA


class GraphRAG:

    def __init__(self, neo4j_client):
        self.db = neo4j_client

    def generate_cypher(
        self,
        question
    ):
        unsupported_reason = self._unsupported_question_reason(question)
        if unsupported_reason:
            return f"UNSUPPORTED: {unsupported_reason}"

        prompt = f"""
You are a Neo4j Cypher expert. Generate only valid Cypher queries.

Schema:
{SCHEMA}

CRITICAL RULES:
1. Return ONLY valid JSON - no markdown formatting
2. Do NOT add markdown code blocks (no ```)
3. Only use the exact relationships defined in the schema
4. For multi-condition filters, use comma-separated MATCH clauses, not chained relationships
5. Do NOT connect through nodes that don't have the relationship
6. **MOST IMPORTANT**: When querying by person name (actor, director, writer, producer, etc.):
   - ALWAYS use case-insensitive matching with: WHERE toLower(p.name) = toLower('PersonName')
   - NEVER use direct property filter like {{name: 'PersonName'}}
   - This ensures 'will smith', 'Will Smith', 'WILL SMITH' all match correctly
7. When the question asks for movies, movies list, movie names, titles, or similar:
   - Use RETURN DISTINCT m.title to extract just the title field
   - When asking for details, use RETURN m to get all movie properties
8. Use exact property maps only for Genre and Language values. Match person names and movie
   titles case-insensitively in WHERE clauses.
9. IF A RELATIONSHIP OR NODE DOESN'T EXIST IN SCHEMA, RESPOND WITH:
   {{"cypher": "UNSUPPORTED: <specific reason why this query cannot be supported>"}}
10. Use at most one WHERE clause after each MATCH or WITH. Join multiple predicates with AND.
11. Character family relationships such as spouse, parent, sibling, or child are not stored.
    Never infer them from co-appearance or outside knowledge; respond with UNSUPPORTED.
12. The `order` property exists only on ACTED_IN and means cast order. Never use `order` on a
    crew relationship.
13. Ordinal words in crew occupations are part of the exact `job` value. For example,
    "second assistant director" means directing.job = 'Second Assistant Director'; it does not
    mean directing.job = 'Assistant Director' with directing.order = 2.
14. A character name is never a Person. For "movies where Person played Character", bind the
    Person's ACTED_IN relationship and filter acting.character with case-insensitive CONTAINS.
15. When the question asks for a movie's director, bind DIRECTED and require
    toLower(directing.job) = toLower('Director') so assistant and unit directors are excluded.
16. Never match a movie title with a direct property map such as (m:Movie {{title: 'value'}}).
    Use a case-insensitive WHERE clause. If the user's title may be partial or approximate, use
    toLower(m.title) CONTAINS toLower('UserTitle') and return m.title to identify the match.
17. ALWAYS include a RETURN clause. If you use ORDER BY, LIMIT, or SKIP, place the RETURN
    clause BEFORE these keywords, not after. Example: RETURN m ORDER BY m.title LIMIT 10

Response Format:
{{
  "cypher": "YOUR_CYPHER_QUERY_HERE"
}}

Question:
{question}

Generate the Cypher query now:"""

        response = chat(
            model="qwen2.5-coder:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={"temperature": 0}
        )

        content = response.message.content
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        # Handle empty or invalid responses
        if not content or content.strip() == "":
            return "UNSUPPORTED: Unable to generate a query for this question"

        try:
            parsed = json.loads(content)
            cypher = parsed.get("cypher", "UNSUPPORTED: Invalid response from model")
            
            # Post-process: Ensure Person name filters use case-insensitive matching
            cypher = self._ensure_case_insensitive_matching(cypher)
            cypher = self._ensure_case_insensitive_movie_titles(cypher)
            cypher = self._ensure_case_insensitive_contains(cypher)
            cypher = self._remove_duplicate_where_clauses(cypher)
            cypher = self._fix_missing_return_clause(cypher)
            
            return cypher
        except json.JSONDecodeError:
            return f"UNSUPPORTED: Unable to parse response: {content[:100]}"

    def _unsupported_question_reason(self, question):
        """Identify questions that require relationships absent from the graph."""
        import re

        family_relationship = (
            r"wife|husband|spouse|mother|father|parent|son|daughter|child|"
            r"brother|sister|sibling"
        )
        asks_for_relationship = any(
            re.search(pattern, question, flags=re.IGNORECASE)
            for pattern in (
                rf"\bwhat\s+(?:is|was)\s+the\s+name\s+of\s+the\s+"
                rf"(?:{family_relationship})\s+of\b",
                rf"\bwho\s+(?:is|was)\s+the\s+(?:{family_relationship})\s+of\b",
                rf"\bwho\s+(?:is|was)\s+.+(?:'s|’s)\s+"
                rf"(?:{family_relationship})\b",
            )
        )
        if asks_for_relationship:
            return (
                "character family relationships are not stored in the database"
            )
        return None

    def _ensure_case_insensitive_matching(self, cypher):
        """
        Convert direct Person name filters to case-insensitive WHERE clauses.
        Example: (p:Person {name: 'Will Smith'})-[:ACTED_IN]->... 
        becomes: (p:Person) WHERE toLower(p.name) = toLower('Will Smith') MATCH (p)-[:ACTED_IN]->...
        """
        import re
        
        # Pattern: (p:Person {name: 'SomeName'})-[:RELATIONSHIP]->
        # Replace with: (p:Person) WHERE toLower(p.name) = toLower('SomeName') MATCH (p)-[:RELATIONSHIP]->
        pattern = r'\((\w+):Person\s*\{\s*name:\s*["\']([^"\']+)["\']\s*\}\)\s*(-\[:([^\]]+)\]->)'
        
        def replace_func(match):
            var = match.group(1)
            name = match.group(2)
            relationship_part = match.group(3)
            return f"({var}:Person) WHERE toLower({var}.name) = toLower('{name}') MATCH ({var}){relationship_part}"
        
        cypher = re.sub(pattern, replace_func, cypher)
        
        # Also handle cases where Person filter is at the end (no relationship after it)
        pattern2 = r'\((\w+):Person\s*\{\s*name:\s*["\']([^"\']+)["\']\s*\}\)(?!\s*-)'
        
        def replace_func2(match):
            var = match.group(1)
            name = match.group(2)
            return f"({var}:Person) WHERE toLower({var}.name) = toLower('{name}')"
        
        cypher = re.sub(pattern2, replace_func2, cypher)
        return cypher

    def _ensure_case_insensitive_movie_titles(self, cypher):
        """Convert direct Movie title maps to case-insensitive predicates."""
        import re

        pattern = (
            r"\((\w+):Movie\s*\{\s*title:\s*"
            r"([\"'])([^\"']+)\2\s*\}\)"
        )

        return re.sub(
            pattern,
            lambda match: (
                f"({match.group(1)}:Movie) WHERE "
                f"toLower({match.group(1)}.title) = "
                f"toLower({match.group(2)}{match.group(3)}{match.group(2)})"
            ),
            cypher,
            flags=re.IGNORECASE,
        )

    def _ensure_case_insensitive_contains(self, cypher):
        """
        Normalize string literals compared to toLower(...) with CONTAINS.
        """
        import re

        pattern = r"(toLower\([^)]+\)\s+CONTAINS\s+)(?!toLower\()([\"'])([^\"']+)\2"

        return re.sub(
            pattern,
            lambda match: f"{match.group(1)}toLower({match.group(2)}{match.group(3)}{match.group(2)})",
            cypher,
            flags=re.IGNORECASE
        )

    def _remove_duplicate_where_clauses(self, cypher):
        """Remove an identical WHERE clause repeated before the next clause."""
        import re

        next_clause = (
            r"(?:OPTIONAL\s+MATCH|MATCH|WITH|RETURN|ORDER\s+BY|LIMIT|SKIP|"
            r"UNION|UNWIND|CALL|$)"
        )
        pattern = re.compile(
            rf"\bWHERE\s+(?P<condition>.+?)\s+WHERE\s+(?P=condition)"
            rf"(?=\s+{next_clause})",
            flags=re.IGNORECASE,
        )

        while True:
            updated = pattern.sub(r"WHERE \g<condition>", cypher)
            if updated == cypher:
                return cypher
            cypher = updated

    def _fix_missing_return_clause(self, cypher):
        """Fix queries that have ORDER BY, LIMIT, or SKIP but no RETURN clause."""
        import re

        # Check if query has ORDER BY, LIMIT, or SKIP but no RETURN
        has_order_limit = re.search(r'\b(ORDER\s+BY|LIMIT|SKIP)\b', cypher, re.IGNORECASE)
        has_return = re.search(r'\bRETURN\b', cypher, re.IGNORECASE)

        if has_order_limit and not has_return:
            # Find the main pattern node(s) to return
            # Try to identify the primary variable from MATCH clause
            match_vars = re.findall(r'\((\w+):[A-Z]\w*\)', cypher)
            if match_vars:
                primary_var = match_vars[0]
                # Insert RETURN before ORDER BY/LIMIT/SKIP
                cypher = re.sub(
                    r'(\s)(ORDER\s+BY|LIMIT|SKIP)\b',
                    rf' RETURN {primary_var} \1\2',
                    cypher,
                    count=1,
                    flags=re.IGNORECASE
                )

        return cypher

    def _resolve_approximate_movie_title(self, cypher):
        """Replace a missing exact title with the closest title stored in Neo4j."""
        import re

        pattern = re.compile(
            r"toLower\((?P<variable>\w+)\.title\)\s*=\s*"
            r"toLower\((?P<quote>[\"'])(?P<title>[^\"']+)(?P=quote)\)",
            flags=re.IGNORECASE,
        )
        match = pattern.search(cypher)
        if not match:
            return None

        requested_title = match.group("title")
        escaped_title = requested_title.replace("\\", "\\\\").replace("'", "\\'")
        candidates = self.db.query(
            "MATCH (movie:Movie) "
            f"WHERE toLower(movie.title) CONTAINS toLower('{escaped_title}') "
            "RETURN movie.title AS title "
            f"ORDER BY abs(size(movie.title) - size('{escaped_title}')), movie.title "
            "LIMIT 1"
        )
        if not candidates:
            return None

        resolved_title = candidates[0]["title"]
        if resolved_title.casefold() == requested_title.casefold():
            return None

        quote = match.group("quote")
        escaped_resolved_title = resolved_title.replace("\\", "\\\\").replace(
            quote, f"\\{quote}"
        )
        replacement = (
            f"toLower({match.group('variable')}.title) = "
            f"toLower({quote}{escaped_resolved_title}{quote})"
        )
        return pattern.sub(replacement, cypher, count=1)

    def validate_cypher(
        self,
        cypher
    ):
        import re

        banned = [
            "CREATE",
            "MERGE",
            "DELETE",
            "DETACH",
            "SET",
            "DROP"
        ]

        upper = cypher.upper()

        for keyword in banned:
            # Use word boundary to avoid matching substrings like "DROP" in "BACKDROP"
            if re.search(rf'\b{keyword}\b', upper):
                raise Exception(
                    f"Blocked query: {keyword}\n\nGenerated Cypher:\n{cypher}"
                )

        return True

    def build_context(
        self,
        rows
    ):

        if not rows:
            return "No results found."

        facts = []

        for row in rows:
            formatted_row = {
                key: self._context_value(value)
                for key, value in row.items()
            }
            facts.append(
                json.dumps(
                    formatted_row,
                    ensure_ascii=False,
                    default=str,
                )
            )

        return "\n".join(facts)

    def _context_value(self, value):
        if isinstance(value, Mapping):
            properties = {
                key: self._context_value(item)
                for key, item in value.items()
            }
            labels = getattr(value, "labels", None)
            if labels is not None:
                return {
                    "labels": sorted(labels),
                    "properties": properties,
                }
            return properties
        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                self._context_value(item)
                for item in value
            ]
        return value

    def _required_answer_values(self, value):
        if isinstance(value, Mapping):
            for property_name in ("name", "title"):
                property_value = value.get(property_name)
                if property_value is not None:
                    return [str(property_value)]
            return []
        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                required
                for item in value
                for required in self._required_answer_values(item)
            ]
        if value is None:
            return []
        return [str(value)]

    def answer(
        self,
        question,
        rows
    ):

        if not rows:
            return "No results found."

        result_count = len(rows)
        displayed_rows = rows[:20]
        display_context = self.build_context(displayed_rows)
        if result_count > 20:
            display_context += f"\n... and {result_count - 20} more results"

        prompt = f"""
Answer the question using only the query results below.

The query results are authoritative database facts:
- For scalar or tabular results, include every displayed row and every returned column.
- Preserve the association between all fields on the same result row.
- Do not contradict, correct, reinterpret, or supplement them.
- Do not use outside knowledge.
- When a node or property map is returned, never expose driver representations, element IDs,
  labels, braces, or raw dictionaries. Render a polished profile with a heading and clearly
  labeled paragraphs or bullet points.
- For a person profile, prioritize name, biography, birthday, deathday, place of birth, gender,
  known-for department, aliases, homepage, and IMDb ID. Omit internal IDs, MongoDB fields,
  image paths, and external-link IDs unless the user explicitly requests them.
- For a movie profile, interpret `backdrop_path` as the movie poster URL, despite the property
  name. Label it as the poster, never as a backdrop image.
- A biography may be concisely summarized, but every statement must remain grounded in the
  returned biography and properties.
- If the results contain only a movie title, state that title as the answer without discussing
  actors, characters, or other facts that are not present in the results.

Question: {question}

Query Results (showing {min(20, result_count)} of {result_count} total results):
{display_context}

Answer:"""

        response = chat(
            model="qwen2.5:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={"temperature": 0}
        )

        answer = response.message.content.strip()
        displayed_values = [
            required
            for row in displayed_rows
            for value in row.values()
            for required in self._required_answer_values(value)
        ]

        if any(value not in answer for value in displayed_values):
            return display_context

        return answer

    def ask(
        self,
        question
    ):

        cypher = self.generate_cypher(
            question
        )

        # Check if query is unsupported
        if cypher.startswith("UNSUPPORTED:"):
            return {
                "cypher": cypher,
                "rows": [],
                "answer": f"I cannot answer this question. {cypher}"
            }

        self.validate_cypher(
            cypher
        )

        rows = self.db.query(
            cypher
        )
        if not rows:
            resolved_cypher = self._resolve_approximate_movie_title(cypher)
            if resolved_cypher:
                self.validate_cypher(resolved_cypher)
                resolved_rows = self.db.query(resolved_cypher)
                if resolved_rows:
                    cypher = resolved_cypher
                    rows = resolved_rows

        answer = self.answer(
            question,
            rows
        )

        return {
            "cypher": cypher,
            "rows": rows,
            "answer": answer
        }