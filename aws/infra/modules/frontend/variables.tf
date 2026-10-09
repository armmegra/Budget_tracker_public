variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "web_dir" {
  description = "Absolute path to web/ - the directory holding index.html."
  type        = string
}

variable "api_url" {
  type = string
}

variable "cognito_client_id" {
  type = string
}

variable "cognito_hosted_ui_url" {
  type = string
}

variable "distribution_url" {
  description = <<-EOT
    Set to skip building the CloudFront distribution and use the URL given.

    A new AWS account cannot create CloudFront distributions until AWS verifies
    it, and the console refuses exactly as the API does.
    Everything else in this module is buildable meanwhile, and so is the rest of
    the instance, which only ever needed a URL to point at.

    The bucket, its public-access block, the origin access control and
    index.html are built either way: they cost nothing, they are what the
    distribution will need, and destroying them to rebuild later would risk the
    bucket name being briefly unavailable.

    Empty is the normal case - build the distribution.
  EOT

  type    = string
  default = ""
}
