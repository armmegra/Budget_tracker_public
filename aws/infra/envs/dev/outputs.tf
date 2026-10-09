# Everything needed to use the instance, or to fill in its line of docs/RESOURCES.md.

output "app_url" {
  description = "Open this. With a front end of our own, the SPA and its generated config.js are both served from here; otherwise it is whatever frontend_url named."
  value       = local.frontend_url
}

output "api_url" {
  value = module.api.api_url
}

output "cognito_hosted_ui_url" {
  value = module.auth.hosted_ui_url
}

output "cognito_user_pool_id" {
  description = "Needed to create the one login by hand - Terraform deliberately does not, so no password touches the state file."
  value       = module.auth.user_pool_id
}

output "cognito_client_id" {
  value = module.auth.client_id
}

output "table_name" {
  value = module.storage.table_name
}

output "data_bucket" {
  value = module.storage.data_bucket
}

output "web_bucket" {
  value = module.frontend.web_bucket
}

output "cloudfront_distribution_id" {
  description = "Needed for cache invalidations from CI. Empty when frontend_url is set - the distribution was not built here."
  value       = module.frontend.distribution_id
}

# What web/config.js must contain when this instance builds no front end of its
# own: the three values the page would otherwise be handed. Write it beside
# index.html and serve the directory; the page reads it and overrides its
# built-in placeholders, which is the whole reason config.js exists.
output "frontend_config_js" {
  description = "Only useful when frontend_url is set - paste into web/config.js."
  value = var.frontend_url == "" ? "" : format(
    "window.BUDGET_CONFIG = %s;\n",
    jsonencode({
      domain   = module.auth.hosted_ui_url
      clientId = module.auth.client_id
      api      = module.api.api_url
    })
  )
}

output "lambda_function_name" {
  value = module.compute.function_name
}
