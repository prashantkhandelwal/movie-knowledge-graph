import json

from ollama import chat

from prompts import SCHEMA


class GraphRAG:

    def __init__(self, neo4j_client):
        self.db = neo4j_client

    def generate_cypher(
        self,
        question
    ):

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
8. Use property filters directly: Genre {{name: 'value'}} for genres and languages
9. IF A RELATIONSHIP OR NODE DOESN'T EXIST IN SCHEMA, RESPOND WITH:
   {{"cypher": "UNSUPPORTED: <specific reason why this query cannot be supported>"}}

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
            ]
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
            
            return cypher
        except json.JSONDecodeError:
            return f"UNSUPPORTED: Unable to parse response: {content[:100]}"

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

    def validate_cypher(
        self,
        cypher
    ):

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

            if keyword in upper:
                raise Exception(
                    f"Blocked query: {keyword}"
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
            # Extract values from row dictionary
            values = list(row.values())
            if values:
                facts.append(str(values[0]))

        return "\n".join(facts)

    def answer(
        self,
        question,
        context
    ):

        # Count results
        if context == "No results found.":
            result_count = 0
            display_context = context
        else:
            lines = context.split("\n")
            result_count = len(lines)
            # Limit to top 20 results for the LLM
            if result_count > 20:
                display_context = "\n".join(lines[:20]) + f"\n... and {result_count - 20} more results"
            else:
                display_context = context

        if result_count == 0:
            return "No results found."

        prompt = f"""
Based on the query results, answer the question clearly and concisely.

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
            ]
        )

        return response.message.content

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

        context = self.build_context(
            rows
        )

        answer = self.answer(
            question,
            context
        )

        return {
            "cypher": cypher,
            "rows": rows,
            "answer": answer
        }