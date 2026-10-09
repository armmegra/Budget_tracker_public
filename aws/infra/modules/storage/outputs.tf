output "table_name" {
  description = "Goes into the Lambda's TABLE_NAME environment variable."
  value       = aws_dynamodb_table.data.name
}

output "table_arn" {
  description = "What the Lambda's inline policy is scoped to."
  value       = aws_dynamodb_table.data.arn
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}
