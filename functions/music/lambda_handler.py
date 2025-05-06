import json
import uuid
import base64
from datetime import datetime

import boto3


class MusicHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.musics_storage_bucket_name = "cp-hackathon-backend-musics-bucket"
        self.dynamodb = boto3.resource("dynamodb")
        self.user_settings_db_table_name = (
            "cp-hackathon-backend-user-settings-db-table"
        )
        self.user_settings_table = self.dynamodb.Table(
            self.user_settings_db_table_name
        )
        self.musics_db_table_name = "cp-hackathon-backend-musics-db-table"
        self.musics_table = self.dynamodb.Table(self.musics_db_table_name)
        self.headers = {
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        }

        self.event = None
        self.body = None
        self.user_id = None
        self.username = None
        self.email = None

    def get_400_response(self, code=400, message="Bad Request"):
        return {
            "statusCode": code,
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
            "body": json.dumps(
                {
                    "event": self.event,
                    "message": message,
                    "data": data,
                }
            ),
        }

    def get_user_settings(self):
        response = self.user_settings_table.get_item(
            Key={"user_id": self.user_id},
        )
        item = response.get("Item")
        if item:
            self.username = item.get("username", "")
            self.email = item.get("email", "")
        return {
            "username": self.username,
            "email": self.email,
        }

    def generate_presigned_url(self, s3_key: str) -> str:
        if not s3_key:
            return None
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.musics_storage_bucket_name, "Key": s3_key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )

    def get_music_list(self) -> list[dict]:
        response = self.musics_table.scan()
        items = response.get("Items", [])
        music_list = []
        for item in items:
            music_list.append(
                {
                    "music_id": item.get("music_id", ""),
                    "title": item.get("title", ""),
                    "s3_key": item.get("s3_key", ""),
                    "user_id": item.get("user_id", ""),
                    "presigned_url": self.generate_presigned_url(
                        item.get("s3_key", "")
                    ),
                }
            )
        return music_list

    def get_music_by_id(self, music_id: str) -> dict:
        response = self.musics_table.get_item(
            Key={"music_id": music_id},
        )
        item = response.get("Item")
        if not item:
            return None
        return {
            "music_id": item.get("music_id", ""),
            "title": item.get("title", ""),
            "s3_key": item.get("s3_key", ""),
            "user_id": item.get("user_id", ""),
            "presigned_url": self.generate_presigned_url(
                item.get("s3_key", "")
            ),
        }

    def upload_music(
        self, music_data: bytes, title: str, extension: str
    ) -> dict:
        # Upload the music to S3
        music_id = str(uuid.uuid4())
        s3_key = f"musics/{title}_{music_id}.{extension}"
        self.s3.put_object(
            Bucket=self.musics_storage_bucket_name,
            Key=s3_key,
            Body=music_data,
            ContentType="audio/*",
        )
        # Store the music metadata in DynamoDB
        music = {
            "music_id": music_id,
            "title": title,
            "s3_key": s3_key,
            "user_id": self.user_id,
            "created_at": datetime.now().isoformat(),
        }
        self.musics_table.put_item(Item=music)
        return music

    def delete_music(self, music_id: str):
        # Delete the music from S3
        music = self.get_music_by_id(music_id=music_id)
        if not music:
            return None
        s3_key = music.get("s3_key")
        self.s3.delete_object(
            Bucket=self.musics_storage_bucket_name, Key=s3_key
        )
        # Delete the music metadata from DynamoDB
        self.musics_table.delete_item(Key={"music_id": music_id})
        return True

    def handle_get_music_list(self):
        music_list = self.get_music_list()
        return self.get_200_response(
            message="Music list retrieved successfully",
            data={
                "music_list": music_list,
            },
        )

    def handle_get_music_by_id(self):
        query_params = self.event.get("queryStringParameters", {})
        music_id = query_params.get("music_id")
        if not music_id:
            return self.get_400_response(message="Music ID is required")

        music = self.get_music_by_id(music_id=music_id)
        if not music:
            return self.get_400_response(message="Music not found")

        return self.get_200_response(
            message="Music retrieved successfully",
            data=music,
        )

    def handle_upload_music(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )
        if "music" not in self.body:
            return self.get_400_response(message="Music data is required")
        if "title" not in self.body:
            return self.get_400_response(message="Title is required")
        if "extension" not in self.body:
            return self.get_400_response(message="Extension is required")

        music_data = base64.b64decode(self.body.get("music"))
        title = self.body.get("title")
        extension = self.body.get("extension")
        try:
            music = self.upload_music(music_data, title, extension)
        except Exception as e:
            return self.get_400_response(
                message=f"Failed to upload music, error: {str(e)}",
            )

        return self.get_200_response(
            message="Music uploaded successfully",
            data=music,
        )

    def handle_delete_music(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )
        query_params = self.event.get("queryStringParameters", {})
        music_id = query_params.get("music_id")
        if not music_id:
            return self.get_400_response(message="Music ID is required")

        try:
            self.delete_music(music_id=music_id)
        except Exception as e:
            return self.get_400_response(
                message=f"Failed to delete music, error: {str(e)}",
            )

        return self.get_200_response(
            message="Music deleted successfully",
        )

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
            self.get_user_settings()

        httpMethod = event.get("httpMethod")
        path = event.get("path")
        if path == "/music":
            if httpMethod == "GET":
                response = self.handle_get_music_by_id()
            elif httpMethod == "POST":
                response = self.handle_upload_music()
            elif httpMethod == "DELETE":
                response = self.handle_delete_music()
            else:
                response = self.get_400_response(
                    message="Unsupported HTTP method"
                )
        elif path == "/music/list":
            if httpMethod == "GET":
                response = self.handle_get_music_list()
            else:
                response = self.get_400_response(
                    message="Unsupported HTTP method"
                )
        # Add CORS headers to the response
        response["headers"] = self.headers
        return response


def lambda_handler(event, context):
    music_handler = MusicHandler()
    return music_handler.handle(event, context)
