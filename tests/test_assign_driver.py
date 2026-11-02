
import json
from unittest.mock import Mock

from backend.assign_driver import lambda_function as assign_driver_module


def test_assigns_available_driver_transactionally(monkeypatch):
    drivers = Mock()
    drivers.scan.return_value = {
        "Items": [{"driver_id": "DRV-1", "name": "Jordan", "availability": "AVAILABLE"}]
    }
    drivers.table_name = "DeliveryDrivers"
    client = Mock()
    drivers.meta.client = client

    jobs = Mock()
    jobs.table_name = "DeliveryJobs"
    monkeypatch.setattr(assign_driver_module, "drivers_table", drivers)
    monkeypatch.setattr(assign_driver_module, "jobs_table", jobs)

    result = assign_driver_module.lambda_handler({
        "body": json.dumps({"job_id": "JOB-1"})
    }, None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["driver_id"] == "DRV-1"
    assert body["status"] == "ASSIGNED"
    transaction = client.transact_write_items.call_args.kwargs["TransactItems"]
    assert transaction[0]["Update"]["Key"] == {"job_id": "JOB-1"}
    assert transaction[1]["Update"]["Key"] == {"driver_id": "DRV-1"}


def test_rejects_missing_job_id(monkeypatch):
    drivers = Mock()
    monkeypatch.setattr(assign_driver_module, "drivers_table", drivers)

    result = assign_driver_module.lambda_handler({"body": "{}"}, None)

    assert result["statusCode"] == 400
    drivers.scan.assert_not_called()


def test_returns_not_found_without_available_driver(monkeypatch):
    drivers = Mock()
    drivers.scan.return_value = {"Items": []}
    monkeypatch.setattr(assign_driver_module, "drivers_table", drivers)

    result = assign_driver_module.lambda_handler({
        "body": json.dumps({"job_id": "JOB-1"})
    }, None)

    assert result["statusCode"] == 404
