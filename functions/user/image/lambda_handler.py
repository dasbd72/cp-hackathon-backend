import json
import base64

import boto3


class UserImageHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.image_storage_bucket_name = "raspberrypi-image-storage"

        self.user_id = None
        self.username = None
        self.email = None

    def handle(self, event, context):
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
            if httpMethod == "GET":
                response_data["data"] = self.get_user_image()
            elif httpMethod == "POST":
                response_data["data"] = self.update_user_image(body)
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
                "Access-Control-Allow-Methods": "OPTIONS,POST",
            },
            "body": json.dumps(response_data),
        }
        return response

    def get_user_image(self):
        if self.user_id is None:
            raise ValueError("Unauthorized: No user ID found in claims")

        # Acquire presigned URL for the image
        image_name = f"{self.username}.jpg"
        s3_key = f"roles/{image_name}"
        presigned_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.image_storage_bucket_name, "Key": s3_key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )
        return {
            "image_url": presigned_url,
        }

    def update_user_image(self, body: dict):
        if self.user_id is None:
            raise ValueError("Unauthorized: No user ID found in claims")
        if "image" not in body:
            raise ValueError("Image data is required")

        image = body.get("image")
        image_data = base64.b64decode(image)
        image_name = f"{self.username}.jpg"
        s3_key = f"roles/{image_name}"

        # Upload the image to S3
        self.s3.put_object(
            Bucket=self.image_storage_bucket_name,
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg",
        )
        # Acquire presigned URL for the image
        presigned_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.image_storage_bucket_name, "Key": s3_key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )
        return {
            "image_url": presigned_url,
        }


def lambda_handler(event, context):
    user_image_handler = UserImageHandler()
    return user_image_handler.handle(event, context)
