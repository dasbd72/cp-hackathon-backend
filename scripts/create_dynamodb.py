from .utils import read_confirm_config, get_boto3_session


class DynamoDBCreator:
    def __init__(self, config_path="scripts/config.json"):
        self.config = read_confirm_config(config_path)
        if self.config is None:
            raise ValueError(
                f"Config file not found at {config_path}. Please run update_config.py first."
            )

        self.session = get_boto3_session(self.config)
        self.sts = self.session.client("sts")
        self.dynamodb = self.session.client("dynamodb")

    def create_user_settings_table(self, table_name):
        # Search for existing tables
        table_exists = table_name in self.dynamodb.list_tables()["TableNames"]
        if not table_exists:
            self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        "AttributeName": "user_id",
                        "KeyType": "HASH",
                    },
                ],
                AttributeDefinitions=[
                    {
                        "AttributeName": "user_id",
                        "AttributeType": "S",
                    },
                ],
                ProvisionedThroughput={
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            )
            # Wait for the table to be created
            waiter = self.dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=table_name)
            print(f"Table {table_name} created successfully.")
        else:
            print(f"Table {table_name} already exists.")

        # Search for existing indexes
        index_exists = "username-index" in [
            index["IndexName"]
            for index in self.dynamodb.describe_table(TableName=table_name)[
                "Table"
            ].get("GlobalSecondaryIndexes", [])
        ]
        if not index_exists:
            # Add second attribute username to the table
            self.dynamodb.update_table(
                TableName=table_name,
                AttributeDefinitions=[
                    {
                        "AttributeName": "username",
                        "AttributeType": "S",
                    },
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        "Create": {
                            "IndexName": "username-index",
                            "KeySchema": [
                                {
                                    "AttributeName": "username",
                                    "KeyType": "HASH",
                                },
                            ],
                            "Projection": {
                                "ProjectionType": "ALL",
                            },
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 5,
                                "WriteCapacityUnits": 5,
                            },
                        }
                    }
                ],
            )
            print(f"Index username-index created.")
        else:
            print(f"Index username-index already exists.")

    def create_musics_table(self, table_name):
        # Search for existing tables
        table_exists = table_name in self.dynamodb.list_tables()["TableNames"]
        if not table_exists:
            self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        "AttributeName": "music_id",
                        "KeyType": "HASH",
                    },
                ],
                AttributeDefinitions=[
                    {
                        "AttributeName": "music_id",
                        "AttributeType": "S",
                    },
                ],
                ProvisionedThroughput={
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            )
            # Wait for the table to be created
            waiter = self.dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=table_name)
            print(f"Table {table_name} created successfully.")
        else:
            print(f"Table {table_name} already exists.")

        # Search for existing indexes
        index_exists = "title-index" in [
            index["IndexName"]
            for index in self.dynamodb.describe_table(TableName=table_name)[
                "Table"
            ].get("GlobalSecondaryIndexes", [])
        ]
        if not index_exists:
            # Add second attribute title to the table
            self.dynamodb.update_table(
                TableName=table_name,
                AttributeDefinitions=[
                    {
                        "AttributeName": "title",
                        "AttributeType": "S",
                    },
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        "Create": {
                            "IndexName": "title-index",
                            "KeySchema": [
                                {
                                    "AttributeName": "title",
                                    "KeyType": "HASH",
                                },
                            ],
                            "Projection": {
                                "ProjectionType": "ALL",
                            },
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 5,
                                "WriteCapacityUnits": 5,
                            },
                        }
                    }
                ],
            )
            print(f"Index title-index created.")
        else:
            print(f"Index title-index already exists.")

    def run(self):
        # Create the user settings table
        # and add the username index if it doesn't exist
        self.create_user_settings_table(
            self.config["user_settings_db_table_name"]
        )
        # Create the musics table
        self.create_musics_table(self.config["musics_db_table_name"])


if __name__ == "__main__":
    dynamodb_creator = DynamoDBCreator()
    dynamodb_creator.run()
