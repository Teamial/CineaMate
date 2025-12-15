terraform {
  required_version = ">= 1.6.0"
}

module "base" {
  source = "../../modules/localstack_base"

  project             = "cinemate"
  environment         = "staging"
  region              = "us-east-1"
  localstack_endpoint = var.localstack_endpoint

  database_url       = var.database_url
  backend_secret_key = var.backend_secret_key
}


