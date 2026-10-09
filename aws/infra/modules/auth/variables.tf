variable "name_prefix" {
  type = string
}

variable "account_id" {
  description = "Appended to the hosted-UI domain prefix, which is globally unique."
  type        = string
}

variable "region" {
  description = "Passed in rather than read from a data source, so the issuer URL is explicit."
  type        = string
}

variable "callback_urls" {
  description = "Exact redirect URIs. Cognito matches these character for character, trailing slash included."
  type        = list(string)
}
