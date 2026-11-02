import uuid

from botocore.exceptions import ClientError

from backend.common import drivers_table, get_payload, response


def lambda_handler(event, context):
	try:
		try:
			data = get_payload(event)
		except (TypeError, ValueError):
			return response(400, {"message": "Invalid request body"})

		if not isinstance(data, dict):
			return response(400, {"message": "Invalid request body"})

		name = data.get("name")
		phone = data.get("phone")
		if not isinstance(name, str) or not name.strip():
			return response(400, {"message": "name is required"})
		if not isinstance(phone, str) or not phone.strip():
			return response(400, {"message": "phone is required"})

		driver = {
			"driver_id": f"DRV-{uuid.uuid4().hex[:8].upper()}",
			"name": name.strip(),
			"phone": phone.strip(),
			"availability": "AVAILABLE"
		}
		drivers_table.put_item(
			Item=driver,
			ConditionExpression="attribute_not_exists(driver_id)"
		)

		return response(201, {
			"message": "Driver registered successfully",
			"driver": driver
		})

	except ClientError as error:
		print("AWS error registering driver:", str(error))
		return response(500, {"message": "Unable to register driver"})
	except Exception as error:
		print("Unexpected error registering driver:", str(error))
		return response(500, {"message": "Unable to register driver"})
