import json

from .utils import read_config

CONFIG_PATH = "scripts/config.json"
CONFIG_TEMPLATE = {
    "aws_profile": "default",
    "aws_region": "us-east-1",
    "role_arn": "",
    "user_settings_db_table_name": "cp-hackathon-backend-user-settings-db-table",
    "musics_db_table_name": "cp-hackathon-backend-musics-db-table",
    "lambda_bucket_name": "cp-hackathon-backend-lambda-bucket",
    "musics_bucket_name": "cp-hackathon-backend-musics-bucket",
    "api_name": "cp-hackathon-backend-api",
    "cognito_user_pool_name": "cp-hackathon-backend-user-pool",
    "cognito_user_pool_client_name": "cp-hackathon-backend-user-pool-client",
    "callback_urls": [
        "http://localhost:4200",
    ],
    "logout_urls": [
        "http://localhost:4200",
    ],
    "authorizer_name": "cp-hackathon-backend-authorizer",
}


def main():
    # Read old config if it exists, and update it,
    # otherwise create a new one
    config = read_config(CONFIG_PATH)
    if config is None:
        config = CONFIG_TEMPLATE
    else:
        # Update config with default values if they are missing
        for key in CONFIG_TEMPLATE:
            if key not in config:
                config[key] = CONFIG_TEMPLATE[key]
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


if __name__ == "__main__":
    main()
