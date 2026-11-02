terraform {
  required_version = ">= 1.10.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  lambda_handlers = {
    create_delivery = "backend.create_delivery.lambda_function.lambda_handler"
    assign_driver   = "backend.assign_driver.lambda_function.lambda_handler"
    register_driver = "backend.register_driver.lambda_function.lambda_handler"
    get_deliveries  = "backend.get_deliveries.lambda_function.lambda_handler"
    update_status   = "backend.update_status.lambda_function.lambda_handler"
    serve_frontend  = "backend.serve_frontend.lambda_function.lambda_handler"
  }
  api_base_url = "https://${aws_apigatewayv2_api.app.id}.execute-api.${var.aws_region}.amazonaws.com"
  api_routes = {
    "GET /"                    = { handler = "serve_frontend", public = true }
    "GET /index.html"          = { handler = "serve_frontend", public = true }
    "GET /script.js"           = { handler = "serve_frontend", public = true }
    "GET /style.css"           = { handler = "serve_frontend", public = true }
    "GET /config.json"         = { handler = "serve_frontend", public = true }
    "POST /drivers"            = { handler = "register_driver", public = false }
    "POST /deliveries"         = { handler = "create_delivery", public = false }
    "POST /deliveries/assign"  = { handler = "assign_driver", public = false }
    "GET /deliveries"          = { handler = "get_deliveries", public = false }
    "PATCH /deliveries/status" = { handler = "update_status", public = false }
  }
}

data "aws_caller_identity" "current" {}

data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/.terraform/backend.zip"
  excludes = [
    ".git/**",
    ".venv/**",
    ".pytest_cache/**",
    "**/__pycache__/**",
    "**/*.pyc",
    ".terraform/**",
    "infrastructure/**",
    "tests/**",
    "frontend/**",
    ".github/**"
  ]
}

resource "aws_dynamodb_table" "jobs" {
  name         = "${local.name_prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = var.enable_deletion_protection
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_dynamodb_table" "drivers" {
  name         = "${local.name_prefix}-drivers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "driver_id"

  attribute {
    name = "driver_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = var.enable_deletion_protection
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambda_handlers
  name              = "/aws/lambda/${local.name_prefix}-${each.key}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_iam_role_policy" "lambda_runtime" {
  name = "${local.name_prefix}-runtime"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:ConditionCheckItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.jobs.arn,
          aws_dynamodb_table.drivers.arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.frontend.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [for group in aws_cloudwatch_log_group.lambda : "${group.arn}:*"]
      }
    ]
  })
}

resource "aws_lambda_function" "backend" {
  for_each         = local.lambda_handlers
  function_name    = "${local.name_prefix}-${each.key}"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = each.value
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = 15
  memory_size      = 256

  environment {
    variables = {
      JOBS_TABLE      = aws_dynamodb_table.jobs.name
      DRIVERS_TABLE   = aws_dynamodb_table.drivers.name
      FRONTEND_BUCKET = aws_s3_bucket.frontend.id
      COGNITO_DOMAIN  = "${var.cognito_domain_prefix}-${var.environment}"
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_runtime,
    aws_cloudwatch_log_group.lambda
  ]
}

resource "aws_cognito_user_pool" "users" {
  name = "${local.name_prefix}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_cognito_user_pool_domain" "users" {
  domain       = "${var.cognito_domain_prefix}-${var.environment}"
  user_pool_id = aws_cognito_user_pool.users.id
}

resource "aws_cognito_user_pool_client" "frontend" {
  name                                 = "${local.name_prefix}-web"
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["${local.api_base_url}/"]
  logout_urls                          = ["${local.api_base_url}/"]
  explicit_auth_flows                  = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  access_token_validity                = 1
  id_token_validity                    = 1
  refresh_token_validity               = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_apigatewayv2_api" "app" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["authorization", "content-type"]
    allow_methods = ["GET", "POST", "PATCH", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.app.id
  authorizer_type  = "JWT"
  name             = "${local.name_prefix}-cognito"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.frontend.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
  }
}

resource "aws_apigatewayv2_integration" "backend" {
  for_each               = local.lambda_handlers
  api_id                 = aws_apigatewayv2_api.app.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.backend[each.key].invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "backend" {
  for_each           = local.api_routes
  api_id             = aws_apigatewayv2_api.app.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.backend[each.value.handler].id}"
  authorization_type = each.value.public ? "NONE" : "JWT"
  authorizer_id      = each.value.public ? null : aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_apigatewayv2_stage" "app" {
  api_id      = aws_apigatewayv2_api.app.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      sourceIp         = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_lambda_permission" "api_gateway" {
  for_each      = local.lambda_handlers
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.app.execution_arn}/*/*"
}

resource "aws_s3_bucket" "frontend" {
  bucket_prefix = "${var.project_name}-${var.environment}-web-"
  force_destroy = false

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "frontend_assets" {
  for_each = fileset("${path.module}/../frontend", "*")
  bucket   = aws_s3_bucket.frontend.id
  key      = each.value
  source   = "${path.module}/../frontend/${each.value}"
  etag     = filemd5("${path.module}/../frontend/${each.value}")
  content_type = lookup({
    "html" = "text/html; charset=utf-8"
    "js"   = "text/javascript; charset=utf-8"
    "css"  = "text/css; charset=utf-8"
  }, reverse(split(".", each.value))[0], "application/octet-stream")
}

resource "aws_s3_object" "frontend_config" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "config.json"
  content_type = "application/json"
  content = jsonencode({
    apiUrl        = local.api_base_url
    region        = var.aws_region
    userPoolId    = aws_cognito_user_pool.users.id
    clientId      = aws_cognito_user_pool_client.frontend.id
    issuer        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
    cognitoDomain = "https://${var.cognito_domain_prefix}-${var.environment}.auth.${var.aws_region}.amazoncognito.com"
    redirectUri   = "${local.api_base_url}/"
  })
  etag = md5(jsonencode({
    apiUrl        = local.api_base_url
    region        = var.aws_region
    userPoolId    = aws_cognito_user_pool.users.id
    clientId      = aws_cognito_user_pool_client.frontend.id
    issuer        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
    cognitoDomain = "https://${var.cognito_domain_prefix}-${var.environment}.auth.${var.aws_region}.amazoncognito.com"
    redirectUri   = "${local.api_base_url}/"
  }))
}
