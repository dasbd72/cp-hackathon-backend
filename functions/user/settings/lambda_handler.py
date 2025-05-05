import json

import boto3


class UserSettingsHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.dynamodb = boto3.resource("dynamodb")
        self.user_settings_db_table_name = (
            "cp-hackathon-backend-user-settings-db-table"
        )
        self.user_settings_table = self.dynamodb.Table(
            self.user_settings_db_table_name
        )

        self.user_id = None
        self.username = None
        self.email = None

    def handle(self, event, context):
        # claims = (
        #     event.get("requestContext", {}).get("authorizer", {}).get("claims")
        # )
        # if claims:
        #     self.user_id = claims.get("sub")
        #     self.username = claims.get("cognito:username")
        #     self.email = claims.get("email")

        # dummy authentication with query string parameters
        self.user_id = self.username = event.get(
            "queryStringParameters", {}
        ).get("username")

        httpMethod = event.get("httpMethod")
        body = json.loads(event.get("body", "{}")) if event.get("body") else {}

        response_data = {
            "event": event,
            "status": "success",
        }
        try:
            if self.user_id is None:
                raise ValueError("Unauthorized: No user ID found in claims")

            if httpMethod == "GET":
                response_data["data"] = self.get_user_settings()
            elif httpMethod == "PUT":
                response_data["data"] = self.update_user_settings(body)
            else:
                raise ValueError(f"Unsupported HTTP method: {httpMethod}")

        except Exception as e:
            response_data["status"] = "error"
            response_data["error"] = str(e)

        response = {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,PUT,GET",
            },
            "body": json.dumps(response_data),
        }
        return response

    def get_user_settings(self):
        response = self.user_settings_table.get_item(
            Key={"user_id": self.user_id},
        )
        item = response.get("Item")
        if item:
            username = item.get("username", "")
            email = item.get("email", "")
        else:
            username = self.username
            email = self.email
        return {
            "username": username,
            "email": email,
        }

    def update_user_settings(self, body: dict):
        if "username" not in body:
            raise ValueError("Missing required field: username")
        if "email" not in body:
            raise ValueError("Missing required field: email")
        username = body.get("username")
        email = body.get("email")
        self.user_settings_table.update_item(
            Key={"user_id": self.user_id},
            UpdateExpression="SET username = :username, email = :email",
            ExpressionAttributeValues={
                ":username": username,
                ":email": email,
            },
            ReturnValues="UPDATED_NEW",
        )
        return {
            "username": username,
            "email": email,
        }


def lambda_handler(event, context):
    user_settings_handler = UserSettingsHandler()
    return user_settings_handler.handle(event, context)
