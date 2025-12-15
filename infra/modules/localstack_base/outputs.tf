output "artifacts_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}

output "events_queue_url" {
  value = aws_sqs_queue.recommendation_events.id
}

output "backend_log_group_name" {
  value = aws_cloudwatch_log_group.backend.name
}

output "ssm_database_url_name" {
  value = aws_ssm_parameter.database_url.name
}

output "backend_secret_arn" {
  value = aws_secretsmanager_secret.backend_secret.arn
}


