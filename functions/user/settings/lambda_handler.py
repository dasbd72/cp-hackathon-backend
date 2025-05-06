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
        self.headers = {
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "OPTIONS,PUT,GET",
        }

        self.event = None
        self.body = None
        self.user_id = None
        self.username = None
        self.email = None

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
        if item:
            self.username = item.get("username", "")
            self.email = item.get("email", "")
        return {
            "username": self.username,
            "email": self.email,
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
            self.username = claims.get("cognito:username")
            self.email = claims.get("email")
            self.get_user_settings(self.user_id)

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
