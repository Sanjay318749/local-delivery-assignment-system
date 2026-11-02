import os

import boto3


s3 = boto3.client("s3")
ALLOWED_ASSETS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/script.js": "script.js",
    "/style.css": "style.css",
    "/config.json": "config.json"
}
CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "script.js": "text/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "config.json": "application/json"
}


def lambda_handler(event, context):
    path = event.get("rawPath", "/")
    asset = ALLOWED_ASSETS.get(path)
    if asset is None:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "text/plain; charset=utf-8"},
            "body": "Not found"
        }

    try:
        result = s3.get_object(
            Bucket=os.environ["FRONTEND_BUCKET"],
            Key=asset
        )
        body = result["Body"].read().decode("utf-8")
        headers = {
            "Content-Type": CONTENT_TYPES[asset],
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; "
                f"connect-src 'self' https://{os.environ['COGNITO_DOMAIN']}"
                f".auth.{os.environ.get('AWS_REGION', 'ap-southeast-1')}"
                ".amazoncognito.com; "
                "style-src 'self'; script-src 'self'; img-src 'self' data:; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
            )
        }
        if asset == "config.json":
            headers["Cache-Control"] = "no-store"
        return {"statusCode": 200, "headers": headers, "body": body}
    except Exception as error:
        print("Error serving frontend asset:", str(error))
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "text/plain; charset=utf-8"},
            "body": "Unable to serve webpage"
        }