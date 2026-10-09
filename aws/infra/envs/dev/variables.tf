variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "env" {
  description = "Environment name. Becomes part of every resource name, so dev and prod cannot collide."
  type        = string
  default     = "dev"
}

variable "project" {
  type    = string
  default = "budget-tracker"
}

variable "extra_callback_urls" {
  description = <<-EOT
    Redirect URIs allowed in addition to the CloudFront one - a local copy of
    index.html served on this port can then sign in against the same pool.
    Empty this list for prod.
  EOT
  type        = list(string)
  default     = ["http://localhost:8000/"]
}

variable "frontend_url" {
  description = <<-EOT
    Where the page will be served from, when Terraform is NOT building the
    CloudFront distribution itself. Set it and the frontend module is skipped
    entirely: Cognito's callback and the API's CORS origin take the value given
    and everything else is built as usual.

    Two reasons it exists. A new AWS account cannot create CloudFront
    distributions until AWS has verified it, and that one refusal blocks nine
    other resources whose only need of CloudFront is a URL to point at. And a
    distribution created by hand can simply be named here.

    "http://localhost:5173" is a legal value: localhost is the one exception to
    Cognito's HTTPS-only rule for callbacks, so the page can be served with
    `python -m http.server 5173 --directory web` against a complete instance
    until the real front end exists. Write web/config.js yourself in that case -
    `terraform output frontend_config_js` prints exactly what it should contain.

    Leave it empty and the frontend module builds the bucket, the distribution
    and config.js as it always has.
  EOT

  type    = string
  default = ""

  validation {
    condition     = var.frontend_url == "" || can(regex("^https://|^http://localhost(:[0-9]+)?$", var.frontend_url))
    error_message = "Must be https://…, or http://localhost[:port] - Cognito refuses any other plain-http callback."
  }
}
