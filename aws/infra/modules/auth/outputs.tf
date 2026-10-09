output "user_pool_id" {
  value = aws_cognito_user_pool.users.id
}

output "client_id" {
  description = "Public by design - it travels in every authorize request."
  value       = aws_cognito_user_pool_client.web.id
}

output "issuer" {
  description = "What the API Gateway JWT authorizer validates tokens against."
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
}

output "hosted_ui_url" {
  value = "https://${aws_cognito_user_pool_domain.hosted.domain}.auth.${var.region}.amazoncognito.com"
}
