
import json
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

from backend.common import (
    drivers_table,
    jobs_table,
    get_payload,
    response
)


def lambda_handler(event, context):

    try:
        # 1. Extract the incoming request
        try:
            data = get_payload(event)
        except (TypeError, ValueError):
            return response(400, {
                "message": "Invalid request body"
            })

        if not isinstance(data, dict):
            return response(400, {
                "message": "Invalid request body"
            })

        job_id = data.get("job_id")

        if not job_id:
            return response(400, {
                "message": "job_id is required"
            })

        # 2. Find an available driver
        result = drivers_table.scan(
            FilterExpression=Attr("availability").eq("AVAILABLE")
        )

        available_drivers = result.get("Items", [])

        # Handle pagination if more records exist
        while result.get("LastEvaluatedKey") and not available_drivers:
            result = drivers_table.scan(
                FilterExpression=Attr("availability").eq("AVAILABLE"),
                ExclusiveStartKey=result["LastEvaluatedKey"]
            )

            available_drivers = result.get("Items", [])

        if not available_drivers:
            return response(404, {
                "message": "No available drivers found"
            })

        # 3. Select the first available driver
        driver = available_drivers[0]

        driver_id = driver["driver_id"]
        driver_name = driver.get("name", "Unknown")

        # 4. Get the DynamoDB client
        dynamodb_client = drivers_table.meta.client

        # 5. Update both records atomically
        dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": jobs_table.table_name,

                        "Key": {
                            "job_id": job_id
                        },

                        "UpdateExpression": (
                            "SET assigned_driver_id = :driver_id, "
                            "#status = :assigned"
                        ),

                        "ConditionExpression": (
                            "#status = :pending"
                        ),

                        "ExpressionAttributeNames": {
                            "#status": "status"
                        },

                        "ExpressionAttributeValues": {
                            ":driver_id": driver_id,
                            ":assigned": "ASSIGNED",
                            ":pending": "PENDING"
                        }
                    }
                },

                {
                    "Update": {
                        "TableName": drivers_table.table_name,

                        "Key": {
                            "driver_id": driver_id
                        },

                        "UpdateExpression": (
                            "SET #availability = :busy"
                        ),

                        "ConditionExpression": (
                            "#availability = :available"
                        ),

                        "ExpressionAttributeNames": {
                            "#availability": "availability"
                        },

                        "ExpressionAttributeValues": {
                            ":busy": "BUSY",
                            ":available": "AVAILABLE"
                        }
                    }
                }
            ]
        )

        # 6. Return successful response
        return response(200, {
            "message": "Driver assigned successfully",
            "job_id": job_id,
            "driver_id": driver_id,
            "driver_name": driver_name,
            "status": "ASSIGNED"
        })

    except ClientError as e:

        # 7. Print detailed AWS error information
        print("AWS Error:", str(e))

        error_response = e.response

        print(
            "Cancellation Reasons:",
            error_response.get("CancellationReasons")
        )

        print(
            "AWS Error Details:",
            error_response.get("Error")
        )

        return response(500, {
            "message": "Unable to assign driver",
        })

    except Exception as e:

        print("Unexpected Error:", str(e))

        return response(500, {
            "message": "Unexpected error while assigning driver",
            "error": str(e)
        })
