variable "localstack_endpoint" {
  type        = string
  description = "LocalStack edge endpoint"
  default     = "http://localhost:4566"
}

variable "database_url" {
  type        = string
  description = "Database URL for this environment"
  default     = "postgresql://postgres:postgres@localhost:5433/movies_db"
}

variable "backend_secret_key" {
  type        = string
  description = "SECRET_KEY for backend auth (emulated secret)"
  sensitive   = true
  default     = "dev-secret-change-me"
}


