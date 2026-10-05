from neo4j import GraphDatabase, Auth


class Neo4jClient:

    def __init__(
        self,
        uri,
        username,
        password,
        database
    ):
        self.database = database
        self.driver = GraphDatabase.driver(
            uri,
            auth=Auth("basic", username, password)
        )

    def query(self, cypher):

        with self.driver.session(database=self.database) as session:
            result = session.run(cypher)

            rows = []

            for record in result:
                rows.append(dict(record))

            return rows

    def close(self):
        self.driver.close()