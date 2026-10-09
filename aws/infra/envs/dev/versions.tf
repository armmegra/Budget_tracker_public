terraform {
  # 1.10 is where native S3 state locking (use_lockfile) landed, which is what
  # lets the backend below work without a DynamoDB lock table.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "budget-tracker"
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}
