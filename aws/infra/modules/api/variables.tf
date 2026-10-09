variable "name_prefix" {
  type = string
}

variable "lambda_invoke_arn" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "jwt_issuer" {
  description = "https://cognito-idp.<region>.amazonaws.com/<pool id>"
  type        = string
}

variable "jwt_audience" {
  description = "The Cognito app client id."
  type        = string
}

variable "allow_origins" {
  description = "Exact origins allowed to call the API from a browser. No scheme-less or wildcard entries."
  type        = list(string)
}

variable "access_log_group_arn" {
  description = "Optional CloudWatch log group for access logs. Null leaves them off, as the console default does."
  type        = string
  default     = null
}
