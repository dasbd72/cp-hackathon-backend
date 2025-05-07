import os
import json

import boto3


class HistoryHandler:
    def __init__(self):
        self.s3 = boto3.client("s3")
        self.sts = boto3.client("sts")
        self.image_storage_bucket_name = "raspberrypi-image-storage2"
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
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        }

        self.event = None
        self.body = None
        self.user_id = None

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

    def generate_presigned_url(self, s3_key: str) -> str:
        if not s3_key:
            return None
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.image_storage_bucket_name, "Key": s3_key},
            ExpiresIn=3600,  # URL valid for 1 hour
        )

    def get_decoded_list(self, limit=40):
        response = self.s3.list_objects(
            Bucket=self.image_storage_bucket_name,
            Prefix="decoded/",
        )
        contents = response.get("Contents", [])
        decoded_list = []
        for item in contents:
            # Filter out directories
            s3_key = item["Key"]
            if s3_key.endswith("/"):
                continue
            # Get the last modified date
            last_modified = item["LastModified"].strftime("%Y-%m-%d %H:%M:%S")
            decoded_list.append(
                {
                    "s3_key": s3_key,
                    "last_modified": last_modified,
                }
            )
        # Sort the list by s3_key in descending order
        decoded_list.sort(key=lambda x: x["s3_key"], reverse=True)
        # Get only the first limit items
        decoded_list = decoded_list[:limit]
        # Generate presigned URLs for each item
        for item in decoded_list:
            item["presigned_url"] = self.generate_presigned_url(item["s3_key"])
        return decoded_list

    def get_results_by_decoded_key(self, decoded_key: str):
        try:
            results_key = decoded_key.replace("decoded/", "results/")
            results_key = os.path.splitext(results_key)[0]
            results_key = results_key + "_match.json"
            # Read the results file from S3
            response = self.s3.get_object(
                Bucket=self.image_storage_bucket_name, Key=results_key
            )
            results = json.loads(response["Body"].read().decode("utf-8"))
        except Exception as e:
            results = {
                "error": str(e),
                "message": "Error retrieving results for key: {}".format(
                    results_key
                ),
            }
        return results

    def handle_get_history_list(self):
        decoded_list = self.get_decoded_list()
        history_list = []
        for item in decoded_list:
            # Get the results for each decoded image
            results = self.get_results_by_decoded_key(item["s3_key"])
            history_list.append(
                {
                    "decoded": item,
                    "results": results,
                }
            )
        return self.get_200_response(
            message="History list retrieved successfully",
            data={
                "history_list": history_list,
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

        httpMethod = event.get("httpMethod")
        path = event.get("path")
        if path == "/history/list":
            if httpMethod == "GET":
                response = self.handle_get_history_list()
            else:
                response = self.get_400_response(
                    message="Unsupported HTTP method"
                )
        else:
            response = self.get_400_response(
                message="Unsupported path: {}".format(path)
            )
        # Add CORS headers to the response
        response["headers"] = self.headers
        return response


def lambda_handler(event, context):
    history_handler = HistoryHandler()
    return history_handler.handle(event, context)
