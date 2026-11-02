import json

from backend.common import jobs_table, response


def lambda_handler(event, context):
	try:
		query_parameters = event.get("queryStringParameters") or {}
		if not isinstance(query_parameters, dict):
			return response(400, {"message": "Invalid query parameters"})

		try:
			limit = int(query_parameters.get("limit", "50"))
			if not 1 <= limit <= 100:
				raise ValueError

			scan_parameters = {"Limit": limit}
			cursor = query_parameters.get("last_evaluated_key")
			if cursor:
				start_key = json.loads(cursor)
				if not isinstance(start_key, dict):
					raise ValueError
				scan_parameters["ExclusiveStartKey"] = start_key
		except (TypeError, ValueError, json.JSONDecodeError):
			return response(400, {
				"message": "limit must be 1-100 and last_evaluated_key must be valid JSON"
			})

		result = jobs_table.scan(**scan_parameters)
		return response(200, {
			"deliveries": result.get("Items", []),
			"last_evaluated_key": result.get("LastEvaluatedKey")
		})

	except Exception as error:
		print("Error retrieving deliveries:", str(error))
		return response(500, {"message": "Unable to retrieve deliveries"})
