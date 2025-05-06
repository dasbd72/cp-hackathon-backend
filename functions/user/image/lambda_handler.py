import json
import base64

import boto3


class UserImageHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.image_storage_bucket_name = "raspberrypi-image-storage"
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

    def generate_user_image_presigned_url(self) -> str:
        # Generate a presigned URL for the image
        s3_key = f"roles/{self.username}.jpg"
        presigned_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.image_storage_bucket_name, "Key": s3_key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )
        return presigned_url

    def get_user_image(self):
        s3_key = f"roles/{self.username}.jpg"
        try:
            self.s3.head_object(
                Bucket=self.image_storage_bucket_name, Key=s3_key
            )
        except Exception as e:
            return None
        # If the image exists, return the presigned URL
        presigned_url = self.generate_user_image_presigned_url()
        return presigned_url

    def update_user_image(self, image_data: bytes):
        # Upload the image to S3
        s3_key = f"roles/{self.username}.jpg"
        self.s3.put_object(
            Bucket=self.image_storage_bucket_name,
            Key=s3_key,
            Body=image_data,
            ContentType="image/*",
        )
        # Acquire presigned URL for the image
        presigned_url = self.generate_user_image_presigned_url()
        return presigned_url

    def handle_get_user_image(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )

        presigned_url = self.get_user_image()
        if presigned_url is None:
            return self.get_400_response(
                message="Image not found",
            )
        return self.get_200_response(
            message="Image found",
            data={
                "image_url": presigned_url,
            },
        )

    def handle_update_user_image(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )
        if "image" not in self.body:
            return self.get_400_response(message="Image data is required")

        image_data = base64.b64decode(self.body.get("image"))
        try:
            self.update_user_image(image_data)
        except Exception as e:
            return self.get_400_response(
                message=f"Failed to update image, error: {str(e)}",
            )
        return self.get_200_response(
            message="Image updated successfully",
            data={
                "image_url": self.generate_user_image_presigned_url(),
            },
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
        if httpMethod == "GET":
            response = self.handle_get_user_image()
        elif httpMethod == "POST":
            response = self.handle_update_user_image()
        else:
            response = self.get_400_response(message="Unsupported HTTP method")
        # Add CORS headers to the response
        response["headers"] = self.headers
        return response


def lambda_handler(event, context):
    user_image_handler = UserImageHandler()
    return user_image_handler.handle(event, context)
