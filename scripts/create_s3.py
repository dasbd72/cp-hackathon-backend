from .utils import read_confirm_config, get_boto3_session


class S3Creator:
    def __init__(self, config_path="scripts/config.json"):
        self.config = read_confirm_config(config_path)
        if self.config is None:
            raise ValueError(
                f"Config file not found at {config_path}. Please run update_config.py first."
            )

        self.session = get_boto3_session(self.config)
        self.s3 = self.session.client("s3")

    def create_s3_bucket(self, bucket_name: str):
        # Search for the bucket by name
        response = self.s3.list_buckets()
        bucket_exists = False
        for bucket in response["Buckets"]:
            if bucket["Name"] == bucket_name:
                if bucket_exists:
                    print(
                        f"Bucket with name {bucket_name} already exists, deleting ARN {bucket['Name']}."
                    )
                    self.s3.delete_bucket(Bucket=bucket["Name"])
                else:
                    bucket_exists = True
        # If the bucket is not found, create it
        if not bucket_exists:
            print(
                f"Bucket with name {bucket_name} not found, creating a new one."
            )
            if self.session.region_name == "us-east-1":
                response = self.s3.create_bucket(Bucket=bucket_name)
            else:
                response = self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={
                        "LocationConstraint": self.session.region_name,
                    },
                )
        return bucket_name

    def run(self):
        lambda_bucket_arn = self.create_s3_bucket(
            bucket_name=self.config["lambda_bucket_name"],
        )
        print(f"Lambda bucket name: {lambda_bucket_arn}")

        musics_bucket_arn = self.create_s3_bucket(
            bucket_name=self.config["musics_bucket_name"],
        )
        print(f"Musics bucket name: {musics_bucket_arn}")


if __name__ == "__main__":
    api_creator = S3Creator()
    api_creator.run()
