terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

# ---------------------------------------------------------------------------
# Static hosting. This is the one piece the hand-built instance never got to -
# docs/runbooks has the console version, and this is the same thing in code.
#
# The bucket stays private. CloudFront reaches it through an Origin Access
# Control, so the only way to the files is through the distribution: no public
# bucket, no website endpoint, and HTTPS without buying a certificate.
# ---------------------------------------------------------------------------
locals {
  # Whether this module builds the distribution, or is told where one is.
  # See variable "distribution_url".
  build_cdn = var.distribution_url == ""
}

resource "aws_s3_bucket" "web" {
  bucket = "${var.name_prefix}-web-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "web" {
  count = local.build_cdn ? 1 : 0

  enabled             = true
  default_root_object = "index.html"
  comment             = "${var.name_prefix} SPA"

  # North America and Europe only. The full edge network costs more and this
  # app has one user.
  price_class = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_id                = "web"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  # A single-page app owns its own routing, so any path that is not a real
  # object must still return the page rather than an S3 error document. 403 is
  # what a private bucket answers for a missing key, which is why both are here.
  dynamic "custom_error_response" {
    for_each = [403, 404]

    content {
      error_code            = custom_error_response.value
      response_code         = 200
      response_page_path    = "/index.html"
      error_caching_min_ttl = 10
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Only this distribution may read the bucket. The SourceArn condition is what
# stops any other CloudFront distribution, in any account, from being pointed
# at these objects.
data "aws_iam_policy_document" "web" {
  count = local.build_cdn ? 1 : 0

  statement {
    sid     = "AllowThisDistributionOnly"
    actions = ["s3:GetObject"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    resources = ["${aws_s3_bucket.web.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  count = local.build_cdn ? 1 : 0

  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web[0].json

  # The public access block must land first or S3 can reject the policy.
  depends_on = [aws_s3_bucket_public_access_block.web]
}

# ---------------------------------------------------------------------------
# The app itself, plus a generated config.
#
# index.html ships with the hand-built instance's ids compiled in as defaults;
# config.js overrides them with whatever this instance actually created, which
# is what lets one HTML file serve dev, prod and a local copy without edits.
# ---------------------------------------------------------------------------
resource "aws_s3_object" "index" {
  bucket       = aws_s3_bucket.web.id
  key          = "index.html"
  source       = "${var.web_dir}/index.html"
  etag         = filemd5("${var.web_dir}/index.html")
  content_type = "text/html; charset=utf-8"

  # The page is one file and changes often; caching it at the edge would mean
  # invalidating on every deploy. The assets it would cache are inline anyway.
  cache_control = "no-cache"
}

# The manual, beside the page that links to it. Rendered from docs/GUIDE.md by
# scripts/manual.py and committed, so a deploy needs no build step - the same
# reason index.html is one file with nothing to bundle.
resource "aws_s3_object" "guide" {
  bucket        = aws_s3_bucket.web.id
  key           = "guide.html"
  source        = "${var.web_dir}/guide.html"
  etag          = filemd5("${var.web_dir}/guide.html")
  content_type  = "text/html; charset=utf-8"
  cache_control = "no-cache"
}

resource "aws_s3_object" "config" {
  bucket        = aws_s3_bucket.web.id
  key           = "config.js"
  content_type  = "application/javascript"
  cache_control = "no-cache"

  content = "window.BUDGET_CONFIG = ${jsonencode({
    domain   = var.cognito_hosted_ui_url
    clientId = var.cognito_client_id
    api      = var.api_url
  })};\n"
}
