# ---------------------------------------------------------------------------
# The dev instance, whole.
#
# One root module per directory rather than Terraform workspaces: workspaces
# share a backend key, and a careless apply in the wrong one is silent. prod is
# a copy of this directory with a different env and backend key.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project}-${var.env}"

  # Repo root, from this directory: infra/envs/dev -> ../../..
  repo_root = abspath("${path.module}/../../..")

  # Where the page is served from. See variable "frontend_url": a new account
  # cannot create a CloudFront distribution until AWS verifies it - the console
  # refuses exactly as the API does - and without this
  # that one refusal takes eight unrelated resources down with it, none of which
  # needs CloudFront for anything but a URL to point at.
  #
  # The frontend module is still built either way. Only its distribution and
  # the bucket policy naming that distribution are skipped, so the bucket, its
  # public-access block, the origin access control and index.html stay exactly
  # where the half-finished apply left them - nothing is destroyed to be
  # rebuilt, and no S3 bucket name has to be surrendered and reclaimed.
  frontend_url = module.frontend.url

  # The SPA is served from the site root, so the redirect URI is the origin
  # plus a slash. Cognito compares these strings exactly - and the CORS origin
  # below must NOT have the slash, because an Origin header never carries one.
  callback_urls = concat(["${local.frontend_url}/"], var.extra_callback_urls)
}

module "storage" {
  source = "../../modules/storage"

  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
}

module "compute" {
  source = "../../modules/compute"

  name_prefix = local.name_prefix
  source_dir  = "${local.repo_root}/src"
  table_name  = module.storage.table_name
  table_arn   = module.storage.table_arn
}

module "auth" {
  source = "../../modules/auth"

  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  region      = var.region

  # Reaches forward to the frontend module. That is not a cycle: Terraform
  # builds its graph from resources, not module boundaries, and the CloudFront
  # distribution depends only on the web bucket - never on Cognito. The reverse
  # edge (config.js needs the client id) closes on a different resource.
  callback_urls = local.callback_urls
}

module "api" {
  source = "../../modules/api"

  name_prefix          = local.name_prefix
  lambda_invoke_arn    = module.compute.invoke_arn
  lambda_function_name = module.compute.function_name
  jwt_issuer           = module.auth.issuer
  jwt_audience         = module.auth.client_id
  allow_origins        = [local.frontend_url]
}

module "frontend" {
  source = "../../modules/frontend"

  name_prefix = local.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  web_dir     = "${local.repo_root}/web"

  api_url               = module.api.api_url
  cognito_client_id     = module.auth.client_id
  cognito_hosted_ui_url = module.auth.hosted_ui_url

  distribution_url = var.frontend_url
}
