
import os
import json
import boto3

# Get AWS region from environment variables
AWS_REGION = os.environ.get(
    "AWS_REGION",
    os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")
)

# Connect to DynamoDB
dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

# Get DynamoDB table names
DRIVERS_TABLE = os.environ.get(
    "DRIVERS_TABLE",
    "DeliveryDrivers"
)

JOBS_TABLE = os.environ.get(
    "JOBS_TABLE",
    "DeliveryJobs"
)

# Connect to individual tables
drivers_table = dynamodb.Table(DRIVERS_TABLE)
jobs_table = dynamodb.Table(JOBS_TABLE)


# Extract request data
def get_payload(event):
    body = event.get("body", event)

    if isinstance(body, str):
        return json.loads(body)

    return body


# Generate API response
def response(status_code, data):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(data)
    }
