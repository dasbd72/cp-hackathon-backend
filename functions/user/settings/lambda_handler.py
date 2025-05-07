import json

import boto3


class UserSettingsHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.sts = boto3.client("sts")
        self.dynamodb = boto3.resource("dynamodb")
        account_id = self.sts.get_caller_identity().get("Account")
        self.user_settings_db_table_name = (
            f"cp-hackathon-{account_id}-backend-user-settings-db-table"
        )
        self.user_settings_table = self.dynamodb.Table(
            self.user_settings_db_table_name
        )
        self.headers = {
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "OPTIONS,PUT,GET",
        }

        self.event = None
        self.body = None
        self.user_id = None

    def get_400_response(self, code=400, message="Bad Request"):
        return {
            "statusCode": code,
            "headers": self.headers,
            "body": json.dumps(
                {
                    "event": self.event,
                    "error": message,
                }
            ),
        }

    def get_200_response(self, message="", data={}):
        return {
            "statusCode": 200,
            "headers": self.headers,
            "body": json.dumps(
                {
                    "event": self.event,
                    "message": message,
                    "data": data,
                }
            ),
        }

    def get_user_settings(self, user_id):
        response = self.user_settings_table.get_item(
            Key={"user_id": user_id},
        )
        item = response.get("Item")
        username = ""
        email = ""
        music_id = ""
        if item:
            username = item.get("username", "")
            email = item.get("email", "")
            music_id = item.get("music_id", "")
        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "music_id": music_id,
        }

    def update_user_settings(self, body: dict):
        if "username" not in body:
            raise ValueError("Missing required field: username")
        if "email" not in body:
            raise ValueError("Missing required field: email")
        if "music_id" not in body:
            raise ValueError("Missing required field: music_id")
        username = body.get("username")
        email = body.get("email")
        music_id = body.get("music_id")
        self.user_settings_table.update_item(
            Key={"user_id": self.user_id},
            UpdateExpression="SET username = :username, email = :email, music_id = :music_id",
            ExpressionAttributeValues={
                ":username": username,
                ":email": email,
                ":music_id": music_id,
            },
            ReturnValues="UPDATED_NEW",
        )
        return {
            "user_id": self.user_id,
            "username": username,
            "email": email,
            "music_id": music_id,
        }

    def handle_get_user_settings(self):
        query_params = self.event.get("queryStringParameters")
        if not query_params:
            query_params = {}
        if "user_id" not in query_params:
            return self.get_400_response(
                message="user_id is required in query parameters"
            )
        user_id = query_params.get("user_id")
        data = self.get_user_settings(user_id)
        return self.get_200_response(message="Settings retrieved", data=data)

    def handle_update_user_settings(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )

        try:
            data = self.update_user_settings(self.body)
        except ValueError as e:
            return self.get_400_response(message=str(e))
        return self.get_200_response(message="Settings updated", data=data)

    def handle(self, event, context):
        self.event = event
        self.body = (
            json.loads(event.get("body", "{}")) if event.get("body") else {}
        )
        claims = (
            event.get("requestContext", {}).get("authorizer", {}).get("claims")
        )
        if claims:
            self.user_id = claims.get("sub")

        httpMethod = event.get("httpMethod")
        if httpMethod == "GET":
            response = self.handle_get_user_settings()
        elif httpMethod == "PUT":
            response = self.handle_update_user_settings()
        else:
            response = self.get_400_response(message="Unsupported HTTP method")
        # Add CORS headers to the response
        response["headers"] = self.headers
        return response


def lambda_handler(event, context):
    user_settings_handler = UserSettingsHandler()
    return user_settings_handler.handle(event, context)
