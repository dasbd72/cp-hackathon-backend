# CP Hackathon Backend

## Deployment

Setup config file first:

```bash
python -m scripts.update_config
```

Then run the following command to deploy the backend:

```bash
python -m scripts.create_s3
python -m scripts.create_dynamodb
python -m scripts.create_lambda
python -m scripts.create_api
```
