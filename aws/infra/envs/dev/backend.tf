terraform {
  # State lives in the bucket made by hand first (docs/RESOURCES.md, item 3),
  # which is deliberately NOT managed here - a bucket cannot hold the state
  # that describes itself.
  #
  # use_lockfile writes a .tflock object next to the state instead of taking a
  # DynamoDB lock, so there is no lock table to pay for or forget.
  backend "s3" {
    bucket       = "tfstate-budget-tracker-<unique-suffix>"
    key          = "envs/dev/terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}
