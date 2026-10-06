SCHEMA = """
DATABASE SCHEMA

NODES:
- Movie: {
    id: integer, title: string, isadult: boolean, budget: integer, imdbid: string,
    revenue: integer, runtime: integer, status: string, originallanguage: string,
    originaltitle: string, releasedate: zoned datetime, video: boolean,
    voteaverage: integer or float, votecount: integer
  }
- Genre: {id: integer, name: string}
- Company: {
    id: integer, name: string, country_code: string, country_name: string
  }
- Language: {code: string, name: string}
- Person: {
    id: integer, adult: boolean, gender: string, known_for_department: string,
    name: string, original_name: string
  }

OPTIONAL NODE PROPERTIES:
- Movie.imdbid, Movie.releasedate, Movie.voteaverage, and Movie.votecount may be absent
- Company.country_code and Company.country_name may be absent
- Person.known_for_department may be absent

RELATIONSHIPS:
Movie Relationships:
- (Movie)-[:HAS_GENRE]->(Genre): A movie has/belongs to a genre
- (Movie)-[:PRODUCED_BY]->(Company): A movie is produced by a company
- (Movie)-[:SPOKEN_IN]->(Language): A movie is spoken in a language

Person-to-Movie Relationships:
- (Person)-[:ACTED_IN]->(Movie): A person acted in a movie; `character` is stored on this relationship
- (Person)-[:DIRECTED]->(Movie): A person directed a movie
- (Person)-[:PRODUCED]->(Movie): A person produced a movie
- (Person)-[:WROTE]->(Movie): A person wrote/wrote script for a movie
- (Person)-[:EDITED]->(Movie): A person edited a movie
- (Person)-[:OPERATED_CAMERA]->(Movie): A person was cinematographer
- (Person)-[:SET_LIGHTING]->(Movie): A person did lighting
- (Person)-[:WORKED_ON_SOUND]->(Movie): A person worked on sound design
- (Person)-[:DESIGNED_COSTUME]->(Movie): A person designed costumes
- (Person)-[:DESIGNED_ART]->(Movie): A person designed art/production design
- (Person)-[:CREATED_VFX]->(Movie): A person created visual effects
- (Person)-[:WORKED_AS_CREW]->(Movie): A person worked as crew member

RELATIONSHIP PROPERTIES:
- HAS_GENRE, PRODUCED_BY, and SPOKEN_IN have no properties
- ACTED_IN has: {
    popularity: integer or float, character: string, order: integer,
    credit_id: string, cast_id: integer
  }
- DIRECTED, PRODUCED, WROTE, EDITED, OPERATED_CAMERA, SET_LIGHTING, WORKED_ON_SOUND,
  DESIGNED_COSTUME, DESIGNED_ART, CREATED_VFX, and WORKED_AS_CREW have:
  {
    popularity: integer or float, credit_id: string, job: string,
    department: string
  }
- ACTED_IN.character may be absent; the other listed relationship properties are present
- Cast-specific properties: `character` is the role/character name, `order` is cast order,
  and `cast_id` is the cast credit identifier
- Crew-specific properties: `job` is the person's exact crew job and `department` is the crew department
- Shared credit properties: `credit_id` identifies the credit and `popularity` is the credit popularity value

IMPORTANT RULES:
- Use only the five defined labels: Movie, Person, Genre, Company, and Language.
  There are no Role, Keyword, Country, Actor, Director, Writer, or Producer node labels.
- Use only the relationship types and directions defined above. Movie metadata relationships point
  from Movie to Genre, Company, or Language. Every cast and crew relationship points from Person
  to Movie.
- Determine a person's contribution from the relationship, not from Person.known_for_department:
  ACTED_IN for actors, DIRECTED for directing, PRODUCED for production, WROTE for writing,
  EDITED for editing, OPERATED_CAMERA for camera, SET_LIGHTING for lighting,
  WORKED_ON_SOUND for sound, DESIGNED_COSTUME for costume and make-up,
  DESIGNED_ART for art, CREATED_VFX for visual effects, and WORKED_AS_CREW for general crew.
- Person.known_for_department describes what the person is generally known for; it does not prove
  that person's role on a particular movie.
- DIRECTED includes the broader Directing department. To find the primary director, bind the
  relationship and require toLower(directing.job) = 'director'.
- For a specific crew occupation, bind the appropriate relationship and filter its `job` property
  case-insensitively. The `department` property identifies the broader crew department.
- The `order` property exists only on ACTED_IN and represents cast billing order. No crew
  relationship has an `order` property; never use `order` to rank or qualify crew roles.
- Ordinal words in a crew occupation are part of the exact `job` value, not a numeric position.
  For example, "second assistant director" must filter
  toLower(directing.job) = toLower('Second Assistant Director'). Do not filter for
  job = 'Assistant Director' with order = 2. Likewise, keep job titles such as
  'First Assistant Director', 'Second Second Assistant Director', and 'Second Unit Director'
  distinct.
- A character is the optional `character` property on ACTED_IN. There is no Role node or HAS_ROLE
  relationship. Bind ACTED_IN and search character names with case-insensitive CONTAINS:
  WHERE toLower(acting.character) CONTAINS toLower('CharacterName')
- An actor name and character name in the same question must constrain the same Person and
  ACTED_IN relationship. A character name is never a Person; do not introduce a second Person
  node for the character.
- The graph stores character names but no relationships between characters. Questions asking for
  a character's spouse, parent, child, sibling, friend, enemy, or other narrative relationship are
  unsupported unless the requested fact is directly present in a defined node or relationship
  property. Do not infer such relationships from cast membership, character names, or outside
  knowledge; return UNSUPPORTED with the missing relationship as the reason.
- Match person names and movie titles case-insensitively:
  WHERE toLower(p.name) = toLower('PersonName')
  WHERE toLower(m.title) = toLower('MovieTitle')
- Do not use `*` inside a string as a wildcard. Use CONTAINS, STARTS WITH, or ENDS WITH.
- Use the exact property names from the schema. In particular, use `m.isadult`, `m.imdbid`,
  `m.originallanguage`, `m.originaltitle`, `m.releasedate`, `m.voteaverage`, and `m.votecount`.
- Movie.imdbid, Movie.releasedate, Movie.voteaverage, Movie.votecount,
  Person.known_for_department, Company.country_code, and Company.country_name are optional.
  Queries must tolerate these properties being null or absent.
- Movie.releasedate is a zoned datetime. Compare it with datetime({...}); for example,
  "released after YEAR" means m.releasedate >= datetime({year: YEAR + 1}).
- Movie.voteaverage can be an integer or float. Treat it as a numeric property in comparisons.
- Property maps support equality only. Put ranges, comparisons, case-insensitive checks, and
  null checks in a WHERE clause, never inside a property map.
- Use at most one WHERE clause after a MATCH or WITH clause. Combine multiple predicates in that
  scope with AND; never emit consecutive WHERE clauses.
- Use exact Genre names with (g:Genre {name: 'GenreName'}). Use exact Language codes or names
  with (l:Language {code: 'XX'}) or (l:Language {name: 'LanguageName'}).
- Company can be filtered by name, country_code, or country_name. Country is a Company property,
  not a separate node.
- Distinguish lookup direction from result direction. "Movies by PersonName" filters Person and
  returns Movie; "who worked on MovieTitle" filters Movie and returns Person.
- For multiple independent movie criteria, use separate or comma-separated MATCH patterns joined
  through the same Movie variable. Do not invent shortcut relationships.
- Return DISTINCT entities or scalar values when multiple credits could produce duplicates.
- Use ORDER BY rand() before LIMIT for random results. If the user asks for "some" results without
  specifying a count, return 5 results.

EXAMPLE QUERIES:
- Movies directed by someone: MATCH (p:Person) WHERE toLower(p.name) = toLower('DirectorName') MATCH (p)-[:DIRECTED]->(m:Movie) RETURN DISTINCT m.title
- Director of a movie: MATCH (p:Person)-[directing:DIRECTED]->(m:Movie) WHERE toLower(m.title) = toLower('MovieTitle') AND toLower(directing.job) = toLower('Director') RETURN DISTINCT p.name
- Second assistant directors of a movie: MATCH (p:Person)-[directing:DIRECTED]->(m:Movie) WHERE toLower(m.title) = toLower('MovieTitle') AND toLower(directing.job) = toLower('Second Assistant Director') RETURN DISTINCT p.name
- "Who directed the movie Independence Day?": MATCH (p:Person)-[directing:DIRECTED]->(m:Movie) WHERE toLower(m.title) = toLower('Independence Day') AND toLower(directing.job) = toLower('Director') RETURN DISTINCT p.name
- Movies with an actor: MATCH (p:Person) WHERE toLower(p.name) = toLower('ActorName') MATCH (p)-[:ACTED_IN]->(m:Movie) RETURN DISTINCT m.title
- Movies with a character: MATCH (:Person)-[acting:ACTED_IN]->(m:Movie) WHERE toLower(acting.character) CONTAINS toLower('CharacterName') RETURN DISTINCT m.title
- Movies where an actor plays a character: MATCH (p:Person)-[acting:ACTED_IN]->(m:Movie) WHERE toLower(p.name) = toLower('ActorName') AND toLower(acting.character) CONTAINS toLower('CharacterName') RETURN DISTINCT m.title
- "In which movie Scarlett Johansson has played the character of Black Widow?": MATCH (p:Person)-[acting:ACTED_IN]->(m:Movie) WHERE toLower(p.name) = toLower('Scarlett Johansson') AND toLower(acting.character) CONTAINS toLower('Black Widow') RETURN DISTINCT m.title
- "Name the movie where the Will Smith character was Hiller": MATCH (p:Person)-[acting:ACTED_IN]->(m:Movie) WHERE toLower(p.name) = toLower('Will Smith') AND toLower(acting.character) CONTAINS toLower('Hiller') RETURN DISTINCT m.title
- Random adult movies released after 2020: MATCH (m:Movie) WHERE m.isadult = true AND m.releasedate >= datetime({year: 2021}) RETURN DISTINCT m.title ORDER BY rand() LIMIT 5
- Action movies: MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {name: 'Action'}) RETURN DISTINCT m.title
- Movies directed by someone with a genre: MATCH (p:Person) WHERE toLower(p.name) = toLower('DirectorName') MATCH (p)-[:DIRECTED]->(m:Movie)-[:HAS_GENRE]->(g:Genre {name: 'GenreName'}) RETURN DISTINCT m.title
- Movies with two actors together: MATCH (a1:Person) WHERE toLower(a1.name) = toLower('Actor1Name') MATCH (a1)-[:ACTED_IN]->(m:Movie)<-[:ACTED_IN]-(a2:Person) WHERE toLower(a2.name) = toLower('Actor2Name') RETURN DISTINCT m.title
"""