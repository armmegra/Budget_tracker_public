terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

# ---------------------------------------------------------------------------
# Cognito user pool - the app's own login, unrelated to how the AWS account is
# signed into. Mirrors item 10 of docs/RESOURCES.md.
#
# Free tier is 50,000 monthly active users and does not expire; this pool has
# one. Threat protection is the only per-user billable feature and it is left
# off deliberately.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool" "users" {
  name = "${var.name_prefix}-users"

  # Sign in with an email address rather than a separate username.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # No self-registration: an admin creates the one account that exists. This is
  # the single most important setting in the file - without it anyone who finds
  # the domain can make themselves an account and the JWT authorizer will
  # happily let them in.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # A second factor, required, from an authenticator app. Without these two
  # blocks the pool is created with MFA OFF - not merely un-enforced but
  # unavailable, so setting a preference on a USER answers "User does not have
  # delivery config set to turn on SOFTWARE_TOKEN_MFA". That is what happened
  # here once, and it is the pool that has to offer it first.
  #
  # ON rather than OPTIONAL because optional means nobody has it: this pool has
  # one account, holding one household's finances, and the enrolment is a QR
  # code the hosted login page shows at the next sign-in.
  #
  # TOTP and not SMS. SMS bills per message through SNS, needs an IAM role to
  # send at all, and a SIM is the weaker factor of the two.
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  # Cognito's own emails, free to 50/day. Nothing is sent while sign-up is
  # disabled and the one user is created pre-verified.
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# ---------------------------------------------------------------------------
# App client. Public, no secret: a browser cannot keep one, which is the whole
# reason the SPA uses authorization code + PKCE.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = var.callback_urls
  logout_urls   = var.callback_urls

  # SPA tokens live in sessionStorage and die with the tab, so a long refresh
  # window buys nothing.
  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Without this a wrong password answers with a distinguishable error and the
  # pool becomes a user-enumeration oracle.
  prevent_user_existence_errors = "ENABLED"
}

# ---------------------------------------------------------------------------
# Hosted UI domain. The prefix is globally unique across all of AWS, hence the
# account id. Cognito rejects prefixes containing aws, amazon or cognito.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool_domain" "hosted" {
  domain       = "${var.name_prefix}-${var.account_id}"
  user_pool_id = aws_cognito_user_pool.users.id
}
