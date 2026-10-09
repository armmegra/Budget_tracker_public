terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

# ---------------------------------------------------------------------------
# HTTP API. Mirrors item 11 of docs/RESOURCES.md.
#
# HTTP APIs cost $1.00 per million requests with no hourly charge, so an idle
# one is free - the REST-API alternative is roughly 3.5x the request price and
# carries features this app has no use for.
# ---------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"

  # The SPA is served from CloudFront, a different origin from the API, so the
  # browser preflights every POST. Origins are listed explicitly rather than
  # "*": the JWT check is the real gate, but there is no reason to invite calls
  # from pages we did not write.
  cors_configuration {
    allow_origins  = var.allow_origins
    allow_methods  = ["POST", "OPTIONS"]
    allow_headers  = ["authorization", "content-type"]
    max_age        = 300
    expose_headers = []
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  payload_format_version = "2.0"
}

# ---------------------------------------------------------------------------
# The JWT authorizer. This is the thing that must never be absent, per the
# project's standing rule that the API is never exposed unprotected - not even
# briefly for testing. Terraform creating both in one apply is strictly safer
# than the console, where the route exists for the minutes it takes to click
# the authorizer together.
#
# audience is the app client id: a token minted for a different client of the
# same pool is rejected.
# ---------------------------------------------------------------------------
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.api.id
  name             = "cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = var.jwt_issuer
    audience = [var.jwt_audience]
  }
}

resource "aws_apigatewayv2_route" "post_api" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /api"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"

  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# HTTP APIs auto-deploy, so there is no separate deployment resource and no
# Deploy button to forget.
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  dynamic "access_log_settings" {
    for_each = var.access_log_group_arn == null ? [] : [1]

    content {
      destination_arn = var.access_log_group_arn
      format = jsonencode({
        requestId = "$context.requestId"
        method    = "$context.httpMethod"
        path      = "$context.path"
        status    = "$context.status"
        error     = "$context.authorizer.error"
      })
    }
  }
}

# The console adds this silently when the integration is created; here it is
# explicit. Without it the API returns 500 on every call.
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowInvokeFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
