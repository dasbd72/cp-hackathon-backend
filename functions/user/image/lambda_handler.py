import json
import base64

import boto3


class UserImageHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.image_storage_bucket_name = "raspberrypi-image-storage"
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

    def handle(self, event, context):
        self.event = event
        self.body = (
            json.loads(event.get("body", "{}")) if event.get("body") else {}
        )
        # dummy authentication with query string parameters
        self.user_id = self.username = event.get(
            "queryStringParameters", {}
        ).get("username")

        httpMethod = event.get("httpMethod")
        if httpMethod == "GET":
            response = self.get_user_image()
        elif httpMethod == "POST":
            response = self.update_user_image()
        else:
            response = self.get_400_response(message="Unsupported HTTP method")
        # Add CORS headers to the response
        response["headers"] = self.headers
        return response

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
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )

        # Check if the image exists in S3
        s3_key = f"roles/{self.username}.jpg"
        try:
            self.s3.head_object(
                Bucket=self.image_storage_bucket_name, Key=s3_key
            )
        except Exception as e:
            # If the image does not exist, return a 404 response
            return self.get_400_response(
                message="Image not found",
            )

        # Acquire presigned URL for the image
        presigned_url = self.generate_user_image_presigned_url()
        return self.get_200_response(
            message="Image found",
            data={
                "image_url": presigned_url,
            },
        )

    def update_user_image(self):
        if self.user_id is None:
            return self.get_400_response(
                message="Unauthorized: No user ID found in claims"
            )
        if "image" not in self.body:
            return self.get_400_response(message="Image data is required")

        # Upload the image to S3
        image_data = base64.b64decode(self.body.get("image"))
        s3_key = f"roles/{self.username}.jpg"
        self.s3.put_object(
            Bucket=self.image_storage_bucket_name,
            Key=s3_key,
            Body=image_data,
            ContentType="image/*",
        )
        # Acquire presigned URL for the image
        presigned_url = self.generate_user_image_presigned_url()
        return self.get_200_response(
            message="Image updated successfully",
            data={
                "image_url": presigned_url,
            },
        )


def lambda_handler(event, context):
    user_image_handler = UserImageHandler()
    return user_image_handler.handle(event, context)
