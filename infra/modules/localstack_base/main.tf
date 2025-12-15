provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    s3             = var.localstack_endpoint
    sqs            = var.localstack_endpoint
    logs           = var.localstack_endpoint
    ssm            = var.localstack_endpoint
    secretsmanager = var.localstack_endpoint
    iam            = var.localstack_endpoint
    sts            = var.localstack_endpoint
  }
}

locals {
  name_prefix = "${var.project}-${var.environment}"
}

# These resources are intentionally simple: they prove Terraform + AWS primitives,
# and work well with LocalStack while mirroring real AWS patterns.

resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.name_prefix}-artifacts"
}

resource "aws_sqs_queue" "recommendation_events" {
  name = "${local.name_prefix}-recommendation-events"
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/${var.project}/${var.environment}/backend"
  retention_in_days = 7
}

resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project}/${var.environment}/DATABASE_URL"
  type  = "String"
  value = var.database_url
}

resource "aws_secretsmanager_secret" "backend_secret" {
  name = "${local.name_prefix}-backend-secret-key"
}

resource "aws_secretsmanager_secret_version" "backend_secret_v1" {
  secret_id     = aws_secretsmanager_secret.backend_secret.id
  secret_string = var.backend_secret_key
}


