SCHEMA = """
DATABASE SCHEMA

NODES:
- Movie: {id, title, revenue, runtime, status, originallanguage, originaltitle, releasedate, voteaverage, votecount}
- Genre: {id, name}
- Company: {id, name}
- Language: {code, name}
- Person: {id, name, birthdate, deathdate, biography, popularity}

RELATIONSHIPS:
Movie Relationships:
- (Movie)-[:HAS_GENRE]->(Genre): A movie has/belongs to a genre
- (Movie)-[:PRODUCED_BY]->(Company): A movie is produced by a company
- (Movie)-[:SPOKEN_IN]->(Language): A movie is spoken in a language

Person-to-Movie Relationships:
- (Person)-[:ACTED_IN]->(Movie): A person acted in a movie (actor/actress)
- (Person)-[:DIRECTED]->(Movie): A person directed a movie
- (Person)-[:PRODUCED]->(Movie): A person produced a movie
- (Person)-[:WROTE]->(Movie): A person wrote/wrote script for a movie
- (Person)-[:EDITED]->(Movie): A person edited a movie
- (Person)-[:OPERATED_CAMERA]->(Movie): A person was cinematographer
- (Person)-[:SET_LIGHTING]->(Movie): A person did lighting
- (Person)-[:CREATED]->(Movie): A person created/composed music
- (Person)-[:WORKED_ON_SOUND]->(Movie): A person worked on sound design
- (Person)-[:DESIGNED_COSTUME]->(Movie): A person designed costumes
- (Person)-[:DESIGNED_ART]->(Movie): A person designed art/production design
- (Person)-[:CREATED_VFX]->(Movie): A person created visual effects
- (Person)-[:CONTRIBUTED_TO]->(Movie): A person contributed to a movie (general)
- (Person)-[:WORKED_AS_CREW]->(Movie): A person worked as crew member

IMPORTANT RULES:
- Only use relationships that are defined above
- Use Person node to query by actor, director, writer, producer, etc.
- CRITICAL: When querying by person name, ALWAYS use case-insensitive matching:
  Use WHERE toLower(p.name) = toLower('SearchName') instead of direct {name: 'SearchName'} filters
- To filter movies by multiple criteria, use comma-separated MATCH clauses
- Use Genre {name: 'GenreName'} for genre filters (exact match for genre names)
- Use Language {code: 'XX'} or {name: 'LanguageName'} for language filters (exact match for languages)
- When querying for cast/actors, use: MATCH (p:Person) WHERE toLower(p.name) = toLower('ActorName') MATCH (p)-[:ACTED_IN]->(m:Movie)
- When querying for directors, use: MATCH (p:Person) WHERE toLower(p.name) = toLower('DirectorName') MATCH (p)-[:DIRECTED]->(m:Movie)
- When querying for writers, use: MATCH (p:Person) WHERE toLower(p.name) = toLower('WriterName') MATCH (p)-[:WROTE]->(m:Movie)
- When querying for producers, use: MATCH (p:Person) WHERE toLower(p.name) = toLower('ProducerName') MATCH (p)-[:PRODUCED]->(m:Movie)
- Return DISTINCT m.title when listing movies to avoid duplicates

EXAMPLE QUERIES:
- Movies directed by someone: MATCH (p:Person) WHERE toLower(p.name) = toLower('DirectorName') MATCH (p)-[:DIRECTED]->(m:Movie) RETURN DISTINCT m.title
- Movies with an actor: MATCH (p:Person) WHERE toLower(p.name) = toLower('ActorName') MATCH (p)-[:ACTED_IN]->(m:Movie) RETURN DISTINCT m.title
- Action movies: MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {name: 'Action'}) RETURN DISTINCT m.title
- Movies directed by someone with a genre: MATCH (p:Person) WHERE toLower(p.name) = toLower('DirectorName') MATCH (p)-[:DIRECTED]->(m:Movie)-[:HAS_GENRE]->(g:Genre {name: 'GenreName'}) RETURN DISTINCT m.title
- Movies with two actors together: MATCH (a1:Person) WHERE toLower(a1.name) = toLower('Actor1Name') MATCH (a1)-[:ACTED_IN]->(m:Movie)<-[:ACTED_IN]-(a2:Person) WHERE toLower(a2.name) = toLower('Actor2Name') RETURN DISTINCT m.title
"""