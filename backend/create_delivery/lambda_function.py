
import json
import uuid
from datetime import datetime, timezone

from backend.common import jobs_table, get_payload, response


def lambda_handler(event, context):

    try:
        # 1. Extract incoming request data
        data = get_payload(event)

        if not isinstance(data, dict):
            return response(400, {
                "message": "Invalid request body"
            })

        customer_name = data.get("customer_name")
        pickup_address = data.get("pickup_address")
        delivery_address = data.get("delivery_address")

        # 2. Validate required fields
        if not all(
            isinstance(value, str) and value.strip()
            for value in (customer_name, pickup_address, delivery_address)
        ):
            return response(400, {
                "message": "Customer name, pickup address and delivery address are required"
            })

        customer_name = customer_name.strip()
        pickup_address = pickup_address.strip()
        delivery_address = delivery_address.strip()

        # 3. Generate a unique delivery job ID
        job_id = "JOB-" + str(uuid.uuid4())[:8].upper()

        # 4. Get current UTC time
        created_at = datetime.now(timezone.utc).isoformat()

        # 5. Prepare delivery record
        delivery = {
            "job_id": job_id,
            "customer_name": customer_name,
            "pickup_address": pickup_address,
            "delivery_address": delivery_address,
            "status": "PENDING",
            "assigned_driver_id": None,
            "created_at": created_at
        }

        # 6. Save delivery record in DynamoDB
        jobs_table.put_item(
            Item=delivery,
            ConditionExpression="attribute_not_exists(job_id)"
        )

        # 7. Return successful response
        return response(201, {
            "message": "Delivery job created successfully",
            "delivery": delivery
        })

    except Exception as e:
        print("Error creating delivery:", str(e))

        return response(500, {
            "message": "Unable to create delivery"
        })
