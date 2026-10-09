output "api_url" {
  description = "Base URL. The app posts to <this>/api."

  # The $default stage's invoke_url carries a trailing slash; the SPA appends
  # "/api" to it, and "//api" is a 404.
  value = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
}

output "api_id" {
  value = aws_apigatewayv2_api.api.id
}
