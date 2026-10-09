terraform {
  required_providers {
    aws     = { source = "hashicorp/aws" }
    archive = { source = "hashicorp/archive" }
  }
}

# ---------------------------------------------------------------------------
# The deployment package.
#
# Built from src/ at plan time - no build step, no CI artefact, nothing to keep
# in sync by hand. The dynamic source blocks list .py files explicitly rather
# than zipping the directory, which is what keeps __pycache__ out of the zip
# without relying on the archive provider's exclude-glob behaviour.
#
# Consequence worth knowing: editing any .py file changes the zip hash, so the
# next plan shows a Lambda update. That is the intent - the code and the
# infrastructure move together.
# ---------------------------------------------------------------------------
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/.build/${var.name_prefix}-lambda.zip"

  dynamic "source" {
    # The package and its rules file. Every group, limit and pattern lives in
    # src/budget/rules.toml, so a zip of .py files alone is
    # a Lambda that fails at import. scripts/build.py lists the same two kinds.
    for_each = setunion(
      fileset(var.source_dir, "**/*.py"),
      fileset(var.source_dir, "**/*.toml"),
    )

    content {
      content  = file("${var.source_dir}/${source.value}")
      filename = source.value
    }
  }
}

# ---------------------------------------------------------------------------
# Execution role. Mirrors item 9 of docs/RESOURCES.md, its budget-api-role-*, but scoped
# by Terraform instead of by the console's auto-created default.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "table" {
  statement {
    sid = "OneTableOnly"

    # Exactly what src/budget/dynamo.py calls: query() to read a partition and
    # batch_writer() to save. Nothing deletes, so no DeleteItem.
    actions = [
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
    ]

    resources = [var.table_arn]
  }
}

resource "aws_iam_role_policy" "table" {
  name   = "${var.name_prefix}-table-access"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.table.json
}

data "aws_iam_policy_document" "textract" {
  statement {
    sid     = "SyncOcrOnly"
    actions = ["textract:DetectDocumentText"]

    # Textract's synchronous APIs act on bytes in the request, not on a stored
    # object, so there is no resource ARN to scope to - "*" is the only valid
    # value here. The narrowing that matters is the single action: the async
    # job APIs and the far pricier AnalyzeDocument are not granted.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "textract" {
  name   = "${var.name_prefix}-textract"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.textract.json
}

# ---------------------------------------------------------------------------
# Log group, created before the function.
#
# Lambda makes this by itself on first invocation, with retention set to Never
# Expire - which is the leftover people forget. Declaring it here means
# Terraform owns it, it has a retention, and terraform destroy actually removes
# it.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.13"
  timeout       = var.timeout
  memory_size   = var.memory_size

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = var.table_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}
