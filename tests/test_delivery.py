import json
from unittest.mock import Mock

from botocore.exceptions import ClientError

from backend.update_status import lambda_function as update_status_module


def make_event(job_id, status):
	return {
		"body": json.dumps({
			"job_id": job_id,
			"status": status
		})
	}


def test_updates_assigned_job_to_picked_up(monkeypatch):
	table = Mock()
	table.get_item.return_value = {
		"Item": {
			"job_id": "JOB-1",
			"status": "ASSIGNED"
		}
	}
	table.update_item.return_value = {
		"Attributes": {
			"status": "PICKED_UP"
		}
	}
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "PICKED_UP"),
		None
	)

	assert result["statusCode"] == 200
	assert json.loads(result["body"])["status"] == "PICKED_UP"
	table.update_item.assert_called_once()


def test_rejects_out_of_order_status(monkeypatch):
	table = Mock()
	table.get_item.return_value = {
		"Item": {
			"job_id": "JOB-1",
			"status": "ASSIGNED"
		}
	}
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "IN_TRANSIT"),
		None
	)

	assert result["statusCode"] == 409
	table.update_item.assert_not_called()


def test_returns_not_found_for_missing_job(monkeypatch):
	table = Mock()
	table.get_item.return_value = {}
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "PICKED_UP"),
		None
	)

	assert result["statusCode"] == 404
	table.update_item.assert_not_called()


def test_rejects_unsupported_status(monkeypatch):
	table = Mock()
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "LOST"),
		None
	)

	assert result["statusCode"] == 400
	table.get_item.assert_not_called()


def test_delivery_completion_releases_driver_atomically(monkeypatch):
	table = Mock()
	table.get_item.return_value = {
		"Item": {
			"job_id": "JOB-1",
			"status": "IN_TRANSIT",
			"assigned_driver_id": "DRV-1"
		}
	}
	client = Mock()
	table.meta.client = client
	drivers = Mock()
	drivers.table_name = "DeliveryDrivers"
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)
	monkeypatch.setattr(update_status_module, "drivers_table", drivers, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "DELIVERED"),
		None
	)

	assert result["statusCode"] == 200
	transaction = client.transact_write_items.call_args.kwargs["TransactItems"]
	assert len(transaction) == 2
	assert transaction[0]["Update"]["TableName"] == table.table_name
	assert transaction[0]["Update"]["Key"] == {"job_id": "JOB-1"}
	assert transaction[1]["Update"]["TableName"] == "DeliveryDrivers"
	assert transaction[1]["Update"]["Key"] == {"driver_id": "DRV-1"}
	assert transaction[1]["Update"]["ExpressionAttributeValues"][":available"] == "AVAILABLE"


def test_returns_conflict_when_completion_transaction_is_cancelled(monkeypatch):
	table = Mock()
	table.get_item.return_value = {
		"Item": {
			"job_id": "JOB-1",
			"status": "IN_TRANSIT",
			"assigned_driver_id": "DRV-1"
		}
	}
	client = Mock()
	client.transact_write_items.side_effect = ClientError({
		"Error": {
			"Code": "TransactionCanceledException",
			"Message": "Transaction cancelled"
		},
		"CancellationReasons": [{"Code": "ConditionalCheckFailed"}]
	}, "TransactWriteItems")
	table.meta.client = client
	drivers = Mock()
	drivers.table_name = "DeliveryDrivers"
	monkeypatch.setattr(update_status_module, "jobs_table", table, raising=False)
	monkeypatch.setattr(update_status_module, "drivers_table", drivers, raising=False)

	result = update_status_module.lambda_handler(
		make_event("JOB-1", "DELIVERED"),
		None
	)

	assert result["statusCode"] == 409
