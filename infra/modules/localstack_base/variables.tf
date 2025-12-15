variable "environment" {
  description = "Environment name (staging|production)"
  type        = string
}

variable "project" {
  description = "Project/service name"
  type        = string
  default     = "cinemate"
}

variable "region" {
  description = "AWS region (emulated)"
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "LocalStack edge endpoint"
  type        = string
  default     = "http://localhost:4566"
}

variable "database_url" {
  description = "Database URL to store in SSM for the environment"
  type        = string
}

variable "backend_secret_key" {
  description = "Backend SECRET_KEY to store in Secrets Manager (emulated)"
  type        = string
  sensitive   = true
}


