from datetime import datetime, timezone

from botocore.exceptions import ClientError

from backend.common import drivers_table, get_payload, jobs_table, response


STATUS_TRANSITIONS = {
	"PICKED_UP": "ASSIGNED",
	"IN_TRANSIT": "PICKED_UP",
	"DELIVERED": "IN_TRANSIT"
}


def lambda_handler(event, context):
	try:
		try:
			data = get_payload(event)
		except (TypeError, ValueError):
			return response(400, {"message": "Invalid request body"})

		if not isinstance(data, dict):
			return response(400, {"message": "Invalid request body"})

		job_id = data.get("job_id")
		requested_status = data.get("status")

		if not isinstance(job_id, str) or not job_id.strip():
			return response(400, {"message": "job_id is required"})

		if not isinstance(requested_status, str):
			return response(400, {"message": "status is required"})

		requested_status = requested_status.strip().upper()
		expected_status = STATUS_TRANSITIONS.get(requested_status)
		if expected_status is None:
			return response(400, {
				"message": "status must be PICKED_UP, IN_TRANSIT, or DELIVERED"
			})

		job_id = job_id.strip()
		result = jobs_table.get_item(
			Key={"job_id": job_id},
			ConsistentRead=True
		)
		job = result.get("Item")

		if not job:
			return response(404, {"message": "Delivery job not found"})

		if job.get("status") != expected_status:
			return response(409, {
				"message": "Status transition is not allowed",
				"current_status": job.get("status"),
				"requested_status": requested_status
			})

		updated_at = datetime.now(timezone.utc).isoformat()
		if requested_status == "DELIVERED":
			driver_id = job.get("assigned_driver_id")
			if not driver_id:
				return response(409, {
					"message": "Delivery job has no assigned driver"
				})

			jobs_table.meta.client.transact_write_items(
				TransactItems=[
					{
						"Update": {
							"TableName": jobs_table.table_name,
							"Key": {"job_id": job_id},
							"UpdateExpression": (
								"SET #status = :status, updated_at = :updated_at"
							),
							"ConditionExpression": (
								"#status = :expected_status "
								"AND assigned_driver_id = :driver_id"
							),
							"ExpressionAttributeNames": {
								"#status": "status"
							},
							"ExpressionAttributeValues": {
								":status": requested_status,
								":updated_at": updated_at,
								":expected_status": expected_status,
								":driver_id": driver_id
							}
						}
					},
					{
						"Update": {
							"TableName": drivers_table.table_name,
							"Key": {"driver_id": driver_id},
							"UpdateExpression": (
								"SET #availability = :available"
							),
							"ConditionExpression": (
								"#availability = :busy"
							),
							"ExpressionAttributeNames": {
								"#availability": "availability"
							},
							"ExpressionAttributeValues": {
								":available": "AVAILABLE",
								":busy": "BUSY"
							}
						}
					}
				]
			)
		else:
			jobs_table.update_item(
				Key={"job_id": job_id},
				UpdateExpression=(
					"SET #status = :status, updated_at = :updated_at"
				),
				ConditionExpression="#status = :expected_status",
				ExpressionAttributeNames={"#status": "status"},
				ExpressionAttributeValues={
					":status": requested_status,
					":updated_at": updated_at,
					":expected_status": expected_status
				}
			)

		return response(200, {
			"message": "Delivery status updated successfully",
			"job_id": job_id,
			"status": requested_status,
			"updated_at": updated_at
		})

	except ClientError as error:
		error_code = error.response.get("Error", {}).get("Code")
		cancellation_reasons = error.response.get("CancellationReasons", [])
		is_transaction_conflict = error_code == "TransactionCanceledException" and any(
			reason.get("Code") in {"ConditionalCheckFailed", "TransactionConflict"}
			for reason in cancellation_reasons
		)
		if error_code == "ConditionalCheckFailedException" or is_transaction_conflict:
			return response(409, {
				"message": "Delivery status changed; reload and try again"
			})

		print("AWS error updating delivery status:", str(error))
		return response(500, {"message": "Unable to update delivery status"})

	except Exception as error:
		print("Unexpected error updating delivery status:", str(error))
		return response(500, {"message": "Unable to update delivery status"})
