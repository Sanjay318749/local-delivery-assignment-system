import json
from unittest.mock import Mock

from backend.get_deliveries import lambda_function as get_deliveries_module


def test_returns_deliveries_and_pagination_key(monkeypatch):
    table = Mock()
    table.scan.return_value = {
        "Items": [{"job_id": "JOB-2", "status": "PENDING"}],
        "LastEvaluatedKey": {"job_id": "JOB-2"}
    }
    monkeypatch.setattr(get_deliveries_module, "jobs_table", table, raising=False)

    result = get_deliveries_module.lambda_handler({
        "queryStringParameters": {
            "limit": "25",
            "last_evaluated_key": json.dumps({"job_id": "JOB-1"})
        }
    }, None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["deliveries"] == [{"job_id": "JOB-2", "status": "PENDING"}]
    assert body["last_evaluated_key"] == {"job_id": "JOB-2"}
    table.scan.assert_called_once_with(
        Limit=25,
        ExclusiveStartKey={"job_id": "JOB-1"}
    )


def test_returns_empty_list_when_table_has_no_items(monkeypatch):
    table = Mock()
    table.scan.return_value = {"Items": []}
    monkeypatch.setattr(get_deliveries_module, "jobs_table", table, raising=False)

    result = get_deliveries_module.lambda_handler({}, None)

    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {
        "deliveries": [],
        "last_evaluated_key": None
    }
    table.scan.assert_called_once_with(Limit=50)


def test_rejects_invalid_pagination_parameters(monkeypatch):
    table = Mock()
    monkeypatch.setattr(get_deliveries_module, "jobs_table", table, raising=False)

    result = get_deliveries_module.lambda_handler({
        "queryStringParameters": {
            "limit": "25",
            "last_evaluated_key": "not-json"
        }
    }, None)

    assert result["statusCode"] == 400
    table.scan.assert_not_called()


def test_rejects_limit_over_maximum(monkeypatch):
    table = Mock()
    monkeypatch.setattr(get_deliveries_module, "jobs_table", table, raising=False)

    result = get_deliveries_module.lambda_handler({
        "queryStringParameters": {"limit": "101"}
    }, None)

    assert result["statusCode"] == 400
    table.scan.assert_not_called()