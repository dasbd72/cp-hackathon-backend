import zipfile
import os
import json

from .utils import read_confirm_config, get_boto3_session


class ApiCreator:
    def __init__(self, config_path="scripts/config.json"):
        self.config = read_confirm_config(config_path)
        if self.config is None:
            raise ValueError(
                f"Config file not found at {config_path}. Please run update_config.py first."
            )

        self.session = get_boto3_session(self.config)
        self.sts = self.session.client("sts")
        self.s3 = self.session.client("s3")
        self.lmbda = self.session.client("lambda")
        self.apigateway = self.session.client("apigateway")
        self.cognito = self.session.client("cognito-idp")

    def create_s3_bucket(self, bucket_name: str):
        # Search for the bucket by name
        response = self.s3.list_buckets()
        bucket_arn = None
        for bucket in response["Buckets"]:
            if bucket["Name"] == bucket_name:
                if bucket_arn is not None:
                    print(
                        f"Bucket with name {bucket_name} already exists, deleting ARN {bucket['Name']}."
                    )
                    self.s3.delete_bucket(Bucket=bucket["Name"])
                else:
                    bucket_arn = bucket["Name"]
        # If the bucket is not found, create it
        if bucket_arn is None:
            print(
                f"Bucket with name {bucket_name} not found, creating a new one."
            )
            if self.session.region_name == "us-east-1":
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={
                        "LocationConstraint": self.session.region_name,
                    },
                )
        return bucket_arn

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
            )
            function_arn = response["FunctionArn"]
        else:
            print(f"Function with name {function_name} found, updating it.")
            response = self.lmbda.update_function_code(
                FunctionName=function_name,
                S3Bucket=bucket_name,
                S3Key=bucket_key,
            )
            function_arn = response["FunctionArn"]
        return function_arn

    def create_cognito_user_pool(self) -> str:
        # Search for cognito user pool by ID
        user_pool_id = None
        user_pools = self.cognito.list_user_pools(MaxResults=60)
        for user_pool in user_pools["UserPools"]:
            if user_pool["Name"] == self.config["cognito_user_pool_name"]:
                if user_pool_id is not None:
                    print(
                        f"User pool with name {self.config['cognito_user_pool_name']} already exists, deleting id {user_pool['Id']}."
                    )
                    self.cognito.delete_user_pool(UserPoolId=user_pool["Id"])
                else:
                    user_pool_id = user_pool["Id"]
        # If the user pool is not found, create it
        # Otherwise, update it
        if user_pool_id is None:
            print(
                f"User pool with name {self.config['cognito_user_pool_name']} not found, creating a new one."
            )
            response = self.cognito.create_user_pool(
                PoolName=self.config["cognito_user_pool_name"],
                Schema=[
                    {
                        "Name": "email",
                        "AttributeDataType": "String",
                        "Required": True,
                        "Mutable": True,
                    }
                ],
                Policies={
                    "PasswordPolicy": {
                        "MinimumLength": 8,
                        "RequireUppercase": True,
                        "RequireNumbers": True,
                        "RequireSymbols": False,
                    }
                },
                AutoVerifiedAttributes=["email"],
                AliasAttributes=["email"],
            )
            user_pool_id = response["UserPool"]["Id"]
        else:
            print(
                f"User pool with name {self.config['cognito_user_pool_name']} found, updating it."
            )
            response = self.cognito.update_user_pool(
                UserPoolId=user_pool_id,
                Policies={
                    "PasswordPolicy": {
                        "MinimumLength": 8,
                        "RequireUppercase": True,
                        "RequireNumbers": True,
                        "RequireSymbols": False,
                    }
                },
                AutoVerifiedAttributes=["email"],
            )
        return user_pool_id

    def create_cognito_user_pool_client(self, user_pool_id: str) -> str:
        user_pool_client_id = None
        user_pool_clients = self.cognito.list_user_pool_clients(
            UserPoolId=user_pool_id, MaxResults=60
        )
        for user_pool_client in user_pool_clients["UserPoolClients"]:
            if (
                user_pool_client["ClientName"]
                == self.config["cognito_user_pool_client_name"]
            ):
                if user_pool_client_id is not None:
                    print(
                        f"User pool client with name {self.config['cognito_user_pool_client_name']} already exists, deleting id {user_pool_client['ClientId']}."
                    )
                    self.cognito.delete_user_pool_client(
                        UserPoolId=user_pool_id,
                        ClientId=user_pool_client["ClientId"],
                    )
                else:
                    user_pool_client_id = user_pool_client["ClientId"]
        # If the user pool client is not found, create it
        # Otherwise, update it
        callback_urls = self.config["callback_urls"]
        logout_urls = self.config["logout_urls"]
        if user_pool_client_id is None:
            print(
                f"User pool client with name {self.config['cognito_user_pool_client_name']} not found, creating a new one."
            )
            response = self.cognito.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=self.config["cognito_user_pool_client_name"],
                GenerateSecret=False,
                RefreshTokenValidity=30,  # 30 days
                AccessTokenValidity=60,  # 60 minutes
                IdTokenValidity=60,  # 60 minutes
                TokenValidityUnits={
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "days",
                },
                ExplicitAuthFlows=[
                    "ALLOW_USER_AUTH",
                    "ALLOW_USER_SRP_AUTH",
                    "ALLOW_REFRESH_TOKEN_AUTH",
                ],
                AllowedOAuthFlows=["code"],
                AllowedOAuthScopes=[
                    "email",
                    "openid",
                    "profile",
                    "aws.cognito.signin.user.admin",
                ],
                SupportedIdentityProviders=["COGNITO"],
                CallbackURLs=callback_urls,
                LogoutURLs=logout_urls,
                AllowedOAuthFlowsUserPoolClient=True,
                PreventUserExistenceErrors="ENABLED",
            )
            user_pool_client_id = response["UserPoolClient"]["ClientId"]
        else:
            print(
                f"User pool client with name {self.config['cognito_user_pool_client_name']} found, updating it."
            )
            response = self.cognito.update_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=user_pool_client_id,
                RefreshTokenValidity=30,  # 30 days
                AccessTokenValidity=60,  # 60 minutes
                IdTokenValidity=60,  # 60 minutes
                TokenValidityUnits={
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "days",
                },
                ExplicitAuthFlows=[
                    "ALLOW_USER_AUTH",
                    "ALLOW_USER_SRP_AUTH",
                    "ALLOW_REFRESH_TOKEN_AUTH",
                ],
                AllowedOAuthFlows=["code"],
                AllowedOAuthScopes=[
                    "email",
                    "openid",
                    "profile",
                    "aws.cognito.signin.user.admin",
                ],
                SupportedIdentityProviders=["COGNITO"],
                CallbackURLs=callback_urls,
                LogoutURLs=logout_urls,
                AllowedOAuthFlowsUserPoolClient=True,
                PreventUserExistenceErrors="ENABLED",
            )
        return user_pool_client_id

    def create_cognito_managed_login(
        self, user_pool_id: str, user_pool_client_id: str
    ) -> str:
        # Search for the managed login
        managed_login_id = None
        try:
            response = self.cognito.describe_managed_login_branding_by_client(
                UserPoolId=user_pool_id,
                ClientId=user_pool_client_id,
            )
            managed_login_id = response["ManagedLoginBranding"][
                "ManagedLoginBrandingId"
            ]
        except Exception:
            print(
                f"Managed login branding does not exist, creating a new one."
            )
            response = self.cognito.create_managed_login_branding(
                UserPoolId=user_pool_id,
                ClientId=user_pool_client_id,
                UseCognitoProvidedValues=True,
            )
            managed_login_id = response["ManagedLoginBranding"][
                "ManagedLoginBrandingId"
            ]
        return managed_login_id

    def create_cognito_user_pool_domain(self, user_pool_id: str) -> str:
        # Search for the domain by name
        domain_prefix = f"{user_pool_id.lower().replace('_', '')}"
        domain = f"https://{domain_prefix}.auth.{self.session.region_name}.amazoncognito.com"
        domain_description = None
        try:
            response = self.cognito.describe_user_pool_domain(
                Domain=domain_prefix
            )
            domain_description = response["DomainDescription"]
        except Exception:
            pass
        # If the domain is not found, create it
        # Otherwise, update it
        if not domain_description:
            if domain_description is not None:
                print(
                    f"User pool domain {domain} already exists, deleting it."
                )
                try:
                    self.cognito.delete_user_pool_domain(
                        Domain=domain_prefix,
                        UserPoolId=user_pool_id,
                    )
                except Exception:
                    pass
            self.cognito.create_user_pool_domain(
                Domain=domain_prefix,
                UserPoolId=user_pool_id,
                ManagedLoginVersion=2,
            )
        else:
            print(f"User pool domain {domain} already exists, updating it.")
            self.cognito.update_user_pool_domain(
                Domain=domain_prefix,
                UserPoolId=user_pool_id,
                ManagedLoginVersion=2,
            )
        return domain

    def create_rest_api(self) -> str:
        # Search for the API by name
        response = self.apigateway.get_rest_apis()
        api_id = None
        for api in response["items"]:
            if api["name"] == self.config["api_name"]:
                if api_id is not None:
                    print(
                        f"API with name {self.config['api_name']} already exists, deleting id {api['id']}."
                    )
                    self.apigateway.delete_rest_api(restApiId=api["id"])
                else:
                    api_id = api["id"]
        # If the API is not found, create it
        if api_id is None:
            print(
                f"API with name {self.config['api_name']} not found, creating a new one."
            )
            response = self.apigateway.create_rest_api(
                name=self.config["api_name"],
                description="API for hackathon project",
                minimumCompressionSize=123,
                endpointConfiguration={
                    "types": [
                        "REGIONAL",
                    ]
                },
            )
            api_id = response["id"]
        return api_id

    def create_authorizer(self, api_id: str, user_pool_id: str) -> str:
        # Search for the authorizer by name
        response = self.apigateway.get_authorizers(restApiId=api_id)
        authorizer_id = None
        for authorizer in response["items"]:
            if authorizer["name"] == self.config["authorizer_name"]:
                if authorizer_id is not None:
                    print(
                        f"Authorizer with name {self.config['authorizer_name']} already exists, deleting id {authorizer['id']}."
                    )
                    self.apigateway.delete_authorizer(
                        restApiId=api_id, authorizerId=authorizer["id"]
                    )
                else:
                    authorizer_id = authorizer["id"]
        # If the authorizer is not found, create it
        if authorizer_id is None:
            print(
                f"Authorizer with name {self.config['authorizer_name']} not found, creating a new one."
            )
            response = self.apigateway.create_authorizer(
                restApiId=api_id,
                name=self.config["authorizer_name"],
                type="COGNITO_USER_POOLS",
                providerARNs=[
                    f"arn:aws:cognito-idp:{self.session.region_name}:{self.sts.get_caller_identity()['Account']}:userpool/{user_pool_id}"
                ],
                identitySource="method.request.header.Authorization",
            )
            authorizer_id = response["id"]
        return authorizer_id

    def create_resource(
        self, api_id: str, parent_id: str, resource_path: str
    ) -> str:
        """
        Find the resource by path, if it exists, otherwise create it.
        """
        # Check if the resource already exists
        resources = self.apigateway.get_resources(restApiId=api_id)
        resource = [
            resource
            for resource in resources["items"]
            if resource.get("parentId") == parent_id
            and resource.get("pathPart") == resource_path
        ]
        if resource:
            print(f"Resource {parent_id}:{resource_path} already exists")
            return resource[0]["id"]

        # Create the resource
        print(f"Creating resource {resource_path}")
        response = self.apigateway.create_resource(
            restApiId=api_id,
            parentId=parent_id,
            pathPart=resource_path,
        )
        return response["id"]

    def create_method(
        self,
        api_id: str,
        resource_id: str,
        http_method: str,
        authorizer_id: str = None,
    ):
        """
        Create a method for the resource.
        """
        # Delete the method if it exists
        try:
            self.apigateway.delete_method(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod=http_method,
            )
        except Exception:
            print(
                f"Method {http_method} for resource {resource_id} does not exist, creating a new one."
            )

        # Create the method
        if authorizer_id:
            self.apigateway.put_method(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod=http_method,
                authorizationType="COGNITO_USER_POOLS",
                authorizerId=authorizer_id,
            )
        else:
            self.apigateway.put_method(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod=http_method,
                authorizationType="NONE",
            )
        self.apigateway.put_method_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": False,
                "method.response.header.Access-Control-Allow-Origin": False,
                "method.response.header.Access-Control-Allow-Methods": False,
            },
            responseModels={
                "application/json": "Empty",
            },
        )

    def create_resource_cors(
        self,
        api_id: str,
        resource_id: str,
    ):
        """
        Create CORS for the resource.
        """
        self.create_method(
            api_id=api_id,
            resource_id=resource_id,
            http_method="OPTIONS",
        )
        # Create the user settings options mock integration
        self.apigateway.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            type="MOCK",
            requestTemplates={"application/json": '{"statusCode": 200}'},
        )
        self.apigateway.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "method.response.header.Access-Control-Allow-Origin": "'*'",
                "method.response.header.Access-Control-Allow-Methods": "'OPTIONS,PUT,GET'",
            },
            responseTemplates={"application/json": '{"statusCode": 200}'},
        )

    def deploy_api(self, api_id: str) -> str:
        """
        Deploy the API to a stage.
        """
        # Check if the stage already exists
        response = self.apigateway.get_stages(restApiId=api_id)
        stage_name = "prod"
        for stage in response["item"]:
            if stage["stageName"] == stage_name:
                print(f"Stage {stage_name} already exists")

        # Create the stage
        self.apigateway.create_deployment(
            restApiId=api_id,
            stageName=stage_name,
            description="Production deployment",
        )

        # Build invoke URL
        invoke_url = f"https://{api_id}.execute-api.{self.session.region_name}.amazonaws.com/{stage_name}"
        return invoke_url

    def run(self):
        # Create the S3 bucket
        lambda_bucket_arn = self.create_s3_bucket(
            bucket_name=self.config["lambda_bucket_name"],
        )
        print(f"Lambda bucket ARN: {lambda_bucket_arn}")

        # Compress, Upload, and Create the get user settings lambda function
        user_settings_function_arn = self.create_lambda_function(
            function_name="cp_hackathon_get_user_settings",
            bucket_name=self.config["lambda_bucket_name"],
            bucket_key=self.compress_and_upload_function_code(
                function_path="functions/user/settings",
                bucket_name=self.config["lambda_bucket_name"],
            ),
        )
        print(f"User Settings function ARN: {user_settings_function_arn}")

        # # Create the user pool
        # user_pool_id = self.create_cognito_user_pool()
        # print(f"User Pool ID: {user_pool_id}")

        # # Create the user pool client
        # user_pool_client_id = self.create_cognito_user_pool_client(
        #     user_pool_id=user_pool_id,
        # )
        # print(f"User Pool Client ID: {user_pool_client_id}")

        # # Create the managed login
        # managed_login_id = self.create_cognito_managed_login(
        #     user_pool_id=user_pool_id,
        #     user_pool_client_id=user_pool_client_id,
        # )
        # print("Managed Login ID:", managed_login_id)

        # # Create the user pool domain
        # user_pool_domain = self.create_cognito_user_pool_domain(
        #     user_pool_id=user_pool_id,
        # )
        # print(f"User Pool Domain: {user_pool_domain}")

        # Create the API
        api_id = self.create_rest_api()
        print(f"API ID: {api_id}")

        # Create the authorizer
        # authorizer_id = self.create_authorizer(
        #     api_id=api_id,
        #     user_pool_id=user_pool_id,
        # )
        # print(f"Authorizer ID: {authorizer_id}")

        # Search for resources
        resources = self.apigateway.get_resources(restApiId=api_id)
        root_id = [
            resource
            for resource in resources["items"]
            if resource["path"] == "/"
        ][0]["id"]
        print(f"Root ID: {root_id}")

        # Create the user resource
        user_id = self.create_resource(
            api_id,
            root_id,
            "user",
        )
        print(f"User ID: {user_id}")

        # Create the user settings resource
        user_settings_id = self.create_resource(
            api_id,
            user_id,
            "settings",
        )
        print(f"User Settings ID: {user_settings_id}")

        # Create CORS for the user settings resource
        self.create_resource_cors(
            api_id=api_id,
            resource_id=user_settings_id,
        )

        # Create the user settings methods
        self.create_method(
            api_id=api_id,
            resource_id=user_settings_id,
            http_method="GET",
            # authorizer_id=authorizer_id,
        )
        # Create the user settings integration
        self.apigateway.put_integration(
            restApiId=api_id,
            resourceId=user_settings_id,
            httpMethod="GET",
            type="AWS_PROXY",
            integrationHttpMethod="POST",
            uri=f"arn:aws:apigateway:{self.session.region_name}:lambda:path/2015-03-31/functions/{user_settings_function_arn}/invocations",
            credentials=self.config["role_arn"],
            requestTemplates={"application/json": '{"statusCode": 200}'},
            passthroughBehavior="WHEN_NO_MATCH",
            contentHandling="CONVERT_TO_TEXT",
        )
        self.apigateway.put_integration_response(
            restApiId=api_id,
            resourceId=user_settings_id,
            httpMethod="GET",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "method.response.header.Access-Control-Allow-Origin": "'*'",
                "method.response.header.Access-Control-Allow-Methods": "'GET'",
            },
            responseTemplates={
                "application/json": json.dumps(
                    {
                        "username": "dasbd72",
                        "email": "twbd723@gmail.com",
                    },
                )
            },
        )

        # Create the user settings methods
        self.create_method(
            api_id=api_id,
            resource_id=user_settings_id,
            http_method="PUT",
            # authorizer_id=authorizer_id,
        )
        # Create the user settings integration
        self.apigateway.put_integration(
            restApiId=api_id,
            resourceId=user_settings_id,
            httpMethod="PUT",
            type="AWS_PROXY",
            integrationHttpMethod="POST",
            uri=f"arn:aws:apigateway:{self.session.region_name}:lambda:path/2015-03-31/functions/{user_settings_function_arn}/invocations",
            credentials=self.config["role_arn"],
            requestTemplates={"application/json": '{"statusCode": 200}'},
            passthroughBehavior="WHEN_NO_MATCH",
            contentHandling="CONVERT_TO_TEXT",
        )
        self.apigateway.put_integration_response(
            restApiId=api_id,
            resourceId=user_settings_id,
            httpMethod="PUT",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "method.response.header.Access-Control-Allow-Origin": "'*'",
                "method.response.header.Access-Control-Allow-Methods": "'PUT'",
            },
            responseTemplates={
                "application/json": json.dumps(
                    {
                        "username": "dasbd72",
                        "email": "twbd723@gmail.com",
                    },
                )
            },
        )

        # print("Client ID:", user_pool_client_id)
        # print(
        #     "Authority: ",
        #     f"https://cognito-idp.{self.session.region_name}.amazonaws.com/{user_pool_id}",
        # )

        invoke_url = self.deploy_api(api_id=api_id)
        print(f"Invoke URL: {invoke_url}")


if __name__ == "__main__":
    api_creator = ApiCreator()
    api_creator.run()
