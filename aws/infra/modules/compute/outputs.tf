output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "invoke_arn" {
  description = "The apigatewayv2 integration URI - not the same as the function ARN."
  value       = aws_lambda_function.api.invoke_arn
}

output "role_name" {
  value = aws_iam_role.lambda.name
}
