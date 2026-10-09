# Every resource, and how to remove it

The hand-built instance was made one resource at a time in the console, and each
was written down the moment it existed, with the clicks that remove it. The rule
of that ledger: **if it is not written there, it was not done** — and nothing is
written before it is done. The original names real identifiers and is private;
this is its shape.

Everything idles at $0.00. Nothing here is billed by the hour.

| # | Resource | What it is for | Idle cost | Remove it by |
| --- | --- | --- | --- | --- |
| 1 | S3 data bucket | backups, uploaded screenshots; encrypted, all public access blocked | stored bytes only | empty, then delete |
| 2 | DynamoDB table | the months, the answers, the settings; on-demand | $0 | delete table |
| 3 | S3 bucket for Terraform state | versioned; outside Terraform on purpose | stored bytes only | empty all versions, delete |
| 4 | IAM role for CI | assumed by GitHub Actions through OIDC, limited to one repository | $0 | delete role |
| 5 | IAM OIDC identity provider | lets GitHub get short-lived credentials with no stored keys | $0 | delete after the role that trusts it |
| 6 | AWS Budget | a ceiling with an alert, the tripwire for everything below | $0 | keep |
| 7 | IAM Identity Center | the non-root login used for all console work, MFA enforced | $0 | keep |
| 8 | Root MFA, billing access for IAM | account hygiene | $0 | never remove root MFA |
| 9 | Lambda function, its role, its log group | the engine; log retention 14 days | $0 | function, then role, then **log group** |
| 10 | Cognito user pool, app client, hosted domain | the app's own login; self-registration off, TOTP required | $0 | after the API's authorizer |
| 11 | API Gateway HTTP API | `POST /api` behind a JWT authorizer | $0 | delete API |
| 12 | The Terraform instance | a second, independent copy of 1, 2, 9, 10, 11 | $0 | `terraform destroy` |
| 13 | Amplify Hosting app | the page, uploaded as a zip | free tier | delete app, then the two list entries below |

## Order matters

- **The authorizer before the pool.** With the pool gone, the authorizer rejects
  every request rather than failing usefully.
- **Log groups survive their function.** Deleting a Lambda does not delete its
  role or its logs; the log group is the classic leftover.
- **A page's address lives in two lists.** Hosting the page somewhere new means
  adding the address to the pool's callback and sign-out URLs (with its trailing
  slash) and to the API's CORS origins (without it). Removing the hosting means
  removing both again.
- **Four things stay outside Terraform on purpose** — the state bucket, the CI
  role, the OIDC provider and the budget — so they survive a `terraform destroy`.

## What was built and removed again

A REST API reading a private bucket through an IAM role, as a second way to
serve the page: built by hand, tested, throttled, and torn down the next day in
five steps. Its runbook is [runbooks/rest-api-s3-proxy.md](runbooks/rest-api-s3-proxy.md).
The teardown leaving everything else working is the part worth noting.

## What never built

A CloudFront distribution and the bucket policy naming it. The account had to be
verified before it could add one, the console refused in the same words, and the
support case went unanswered. The Terraform keeps both resources, conditional on
one variable, so they appear the day the account allows them.
