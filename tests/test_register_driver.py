import json
from unittest.mock import Mock

from backend.register_driver import lambda_function as register_driver_module


def test_registers_driver_as_available(monkeypatch):
    table = Mock()
    monkeypatch.setattr(register_driver_module, "drivers_table", table, raising=False)
    event = {
        "body": json.dumps({
            "name": "Jordan Lee",
            "phone": "+15551234567"
        })
    }

    result = register_driver_module.lambda_handler(event, None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 201
    assert body["driver"]["name"] == "Jordan Lee"
    assert body["driver"]["phone"] == "+15551234567"
    assert body["driver"]["availability"] == "AVAILABLE"
    table.put_item.assert_called_once()
    stored_driver = table.put_item.call_args.kwargs["Item"]
    assert stored_driver["driver_id"].startswith("DRV-")


def test_rejects_missing_driver_fields(monkeypatch):
    table = Mock()
    monkeypatch.setattr(register_driver_module, "drivers_table", table, raising=False)

    result = register_driver_module.lambda_handler({"body": json.dumps({"name": "Jordan"})}, None)

    assert result["statusCode"] == 400
    table.put_item.assert_not_called()


def test_rejects_non_object_body(monkeypatch):
    table = Mock()
    monkeypatch.setattr(register_driver_module, "drivers_table", table, raising=False)

    result = register_driver_module.lambda_handler({"body": "[]"}, None)

    assert result["statusCode"] == 400
    table.put_item.assert_not_called()