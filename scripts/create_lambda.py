import zipfile
import os
import json

from .utils import read_confirm_config, get_boto3_session


class LambdaCreator:
    def __init__(self, config_path="scripts/config.json"):
        self.config = read_confirm_config(config_path)
        if self.config is None:
            raise ValueError(
                f"Config file not found at {config_path}. Please run update_config.py first."
            )

        self.session = get_boto3_session(self.config)
        self.s3 = self.session.client("s3")
        self.lmbda = self.session.client("lambda")

    def compress_and_upload_function_code(
        self, function_path: str, bucket_name: str
    ) -> str:
        """
        Compress the function code into a zip file, and upload it to S3.

        Example
        function_path: user/settings/get

        with the following structure:
        user/settings/get/lambda_handler.py
        user/settings/get/lib/*

        into:
        user/settings/get/lambda_handler.zip
        """
        zip_file_path = os.path.join(function_path, "lambda_handler.zip")
        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            # Walk the directory and add files to the zip file
            for root, _, files in os.walk(function_path):
                for file in files:
                    if file.endswith(".zip"):
                        # Skip zip files to avoid recursion
                        continue
                    file_path = os.path.join(root, file)
                    # Add the file to the zip file, preserving the directory structure
                    zipf.write(
                        file_path,
                        os.path.relpath(file_path, function_path),
                    )
        # Upload the zip file to S3
        self.s3.upload_file(
            Filename=zip_file_path,
            Bucket=bucket_name,
            Key=zip_file_path,
        )
        # Delete the zip file after uploading
        os.remove(zip_file_path)
        return zip_file_path

    def create_lambda_function(
        self, function_name: str, bucket_name: str, bucket_key: str
    ) -> str:
        # Search for the function by name
        response = self.lmbda.list_functions()
        function_arn = None
        for function in response["Functions"]:
            if function["FunctionName"] == function_name:
                if function_arn is not None:
                    print(
                        f"Function with name {function_name} already exists, deleting ARN {function['FunctionArn']}."
                    )
                    self.lmbda.delete_function(
                        FunctionName=function["FunctionName"]
                    )
                else:
                    function_arn = function["FunctionArn"]
        # If the function is not found, create it
        # Otherwise, update it
        if function_arn is None:
            print(
                f"Function with name {function_name} not found, creating a new one."
            )
            response = self.lmbda.create_function(
                FunctionName=function_name,
                Runtime="python3.10",
                Role=self.config["role_arn"],
                Handler="lambda_handler.lambda_handler",
                Code={
                    "S3Bucket": bucket_name,
                    "S3Key": bucket_key,
                },
                Timeout=30,
            )
            function_arn = response["FunctionArn"]
        else:
            print(f"Function with name {function_name} found, updating it.")
            self.lmbda.update_function_configuration(
                FunctionName=function_name,
                Role=self.config["role_arn"],
                Handler="lambda_handler.lambda_handler",
                Timeout=30,
            )
            self.lmbda.get_waiter("function_updated").wait(
                FunctionName=function_name,
            )
            self.lmbda.update_function_code(
                FunctionName=function_name,
                S3Bucket=bucket_name,
                S3Key=bucket_key,
            )
        return function_arn

    def run(self):
        # Compress, Upload, and Create the get user settings lambda function
        user_settings_function_arn = self.create_lambda_function(
            function_name=self.config["user_settings_function_name"],
            bucket_name=self.config["lambda_bucket_name"],
            bucket_key=self.compress_and_upload_function_code(
                function_path="functions/user/settings",
                bucket_name=self.config["lambda_bucket_name"],
            ),
        )
        print(f"User Settings function ARN: {user_settings_function_arn}")

        # Compress, Upload, and Create the user image lambda function
        user_image_function_arn = self.create_lambda_function(
            function_name=self.config["user_image_function_name"],
            bucket_name=self.config["lambda_bucket_name"],
            bucket_key=self.compress_and_upload_function_code(
                function_path="functions/user/image",
                bucket_name=self.config["lambda_bucket_name"],
            ),
        )
        print(f"User Image function ARN: {user_image_function_arn}")

        # Compress, Upload, and Create the music lambda function
        get_music_function_arn = self.create_lambda_function(
            function_name=self.config["music_function_name"],
            bucket_name=self.config["lambda_bucket_name"],
            bucket_key=self.compress_and_upload_function_code(
                function_path="functions/music",
                bucket_name=self.config["lambda_bucket_name"],
            ),
        )
        print(f"Music function ARN: {get_music_function_arn}")


if __name__ == "__main__":
    lambda_creator = LambdaCreator()
    lambda_creator.run()
