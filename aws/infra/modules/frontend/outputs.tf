output "domain_name" {
  description = "d111111abcdef8.cloudfront.net - the host the app is reached on. Empty when the distribution was not built here."
  value       = one(aws_cloudfront_distribution.web[*].domain_name)
}

output "url" {
  description = "Where the page is served from: this module's distribution, or whatever distribution_url named."
  value       = local.build_cdn ? "https://${aws_cloudfront_distribution.web[0].domain_name}" : trimsuffix(var.distribution_url, "/")
}

output "web_bucket" {
  value = aws_s3_bucket.web.bucket
}

output "distribution_id" {
  description = "Needed for cache invalidations from CI. Empty when the distribution was not built here."
  value       = one(aws_cloudfront_distribution.web[*].id)
}
