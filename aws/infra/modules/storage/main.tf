terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

# ---------------------------------------------------------------------------
# DynamoDB - the single table the app actually stores everything in.
#
# PK/SK strings, on-demand billing. Mirrors item 2 of docs/RESOURCES.md. On-demand is
# what keeps the idle cost at exactly zero: provisioned capacity bills by the
# hour whether or not anything reads.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "data" {
  name         = "${var.name_prefix}-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # The hand-built table has this off, and a dev instance is meant to be
  # destroyed. prod should flip it to true.
  deletion_protection_enabled = var.deletion_protection

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  # AWS-owned key: free, and the alternative (a customer-managed KMS key) bills
  # $1/month for the key plus per-request charges.
  server_side_encryption {
    enabled = false
  }
}

# ---------------------------------------------------------------------------
# Data bucket.
#
# Mirrors item 1 of docs/RESOURCES.md. Note honestly: no code path writes to it today -
# notes live in the table and screenshots go to Textract as base64 bytes without
# ever landing in S3. It exists because the hand-built instance has it and this
# tree is meant to reproduce that instance. If it is still unused when prod is
# built, delete it from both.
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "data" {
  bucket = "${var.name_prefix}-data-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
