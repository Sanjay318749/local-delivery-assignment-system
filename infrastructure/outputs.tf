output "api_url" {
  description = "Base URL for the authenticated HTTP API."
  value       = aws_apigatewayv2_stage.app.invoke_url
}

output "frontend_url" {
  description = "HTTPS API Gateway URL that serves the web application and API."
  value       = local.api_base_url
}

output "frontend_bucket_name" {
  description = "Private S3 bucket that stores the frontend assets."
  value       = aws_s3_bucket.frontend.id
}

output "user_pool_id" {
  description = "Cognito User Pool ID for user administration."
  value       = aws_cognito_user_pool.users.id
}

output "user_pool_client_id" {
  description = "Public Cognito app client ID used by the browser."
  value       = aws_cognito_user_pool_client.frontend.id
}
