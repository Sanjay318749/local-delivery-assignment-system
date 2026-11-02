from unittest.mock import Mock

from backend.serve_frontend import lambda_function as frontend_module


def test_serves_homepage_from_private_bucket(monkeypatch):
    body = Mock()
    body.read.return_value = b"<html>dispatch</html>"
    s3 = Mock()
    s3.get_object.return_value = {"Body": body}
    monkeypatch.setattr(frontend_module, "s3", s3)
    monkeypatch.setenv("FRONTEND_BUCKET", "private-frontend-bucket")
    monkeypatch.setenv("COGNITO_DOMAIN", "delivery-app-dev")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")

    result = frontend_module.lambda_handler({"rawPath": "/"}, None)

    assert result["statusCode"] == 200
    assert result["headers"]["Content-Type"] == "text/html; charset=utf-8"
    assert result["body"] == "<html>dispatch</html>"
    assert "Content-Security-Policy" in result["headers"]
    s3.get_object.assert_called_once_with(
        Bucket="private-frontend-bucket",
        Key="index.html"
    )


def test_rejects_unlisted_asset_paths():
    result = frontend_module.lambda_handler({"rawPath": "/../../secrets"}, None)

    assert result["statusCode"] == 404