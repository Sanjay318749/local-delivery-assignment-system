variable "aws_region" {
  description = "AWS region for the application stack."
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Lowercase project identifier used in resource names."
  type        = string
  default     = "local-delivery"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-21 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,13}[a-z0-9]$", var.environment))
    error_message = "environment must be 2-15 lowercase letters, digits, or hyphens and start/end with a letter or digit."
  }
}

variable "cognito_domain_prefix" {
  description = "Globally unique base prefix; the environment suffix is appended."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{3,53}[a-z0-9]$", var.cognito_domain_prefix))
    error_message = "cognito_domain_prefix must be 5-55 lowercase letters, digits, or hyphens."
  }
}

variable "lambda_log_retention_days" {
  description = "CloudWatch Logs retention period for Lambda functions."
  type        = number
  default     = 30
}

variable "enable_deletion_protection" {
  description = "Protect DynamoDB tables from accidental deletion."
  type        = bool
  default     = false
}
