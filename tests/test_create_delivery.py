
import json
from unittest.mock import Mock

from backend.create_delivery import lambda_function as create_delivery_module


def test_creates_delivery(monkeypatch):
    table = Mock()
    monkeypatch.setattr(create_delivery_module, "jobs_table", table)
    event = {
        "body": json.dumps({
            "customer_name": "Jordan Lee",
            "pickup_address": "North warehouse",
            "delivery_address": "Market Street"
        })
    }

    result = create_delivery_module.lambda_handler(event, None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 201
    assert body["delivery"]["status"] == "PENDING"
    assert body["delivery"]["job_id"].startswith("JOB-")
    table.put_item.assert_called_once()


def test_rejects_invalid_delivery_body(monkeypatch):
    table = Mock()
    monkeypatch.setattr(create_delivery_module, "jobs_table", table)

    result = create_delivery_module.lambda_handler({"body": "[]"}, None)

    assert result["statusCode"] == 400
    table.put_item.assert_not_called()


def test_rejects_blank_delivery_fields(monkeypatch):
    table = Mock()
    monkeypatch.setattr(create_delivery_module, "jobs_table", table)

    result = create_delivery_module.lambda_handler({
        "body": json.dumps({
            "customer_name": "Jordan",
            "pickup_address": "  ",
            "delivery_address": "Market Street"
        })
    }, None)

    assert result["statusCode"] == 400
    table.put_item.assert_not_called()
