# infra/

The whole application as code. `envs/dev` is a root module; `envs/prod` will be a
copy of it with a different `env` and backend key.

```
infra/
├── modules/
│   ├── storage/   DynamoDB table + data bucket
│   ├── compute/   Lambda, its role, its log group, and the zip built from src/
│   ├── auth/      Cognito pool, app client, hosted-UI domain
│   ├── api/       HTTP API, JWT authorizer, route, stage, invoke permission
│   └── frontend/  Web bucket, CloudFront + OAC, index.html and a generated config.js
└── envs/
    └── dev/       wires the five together
```

Running it is described in this build's README. What follows is the reasoning a
plan file will not tell you.

## What is deliberately not here

Four things in the account are managed by hand, and should stay that way:

| Not managed | Why |
| --- | --- |
| The tfstate bucket | A bucket cannot hold the state that describes itself. |
| GitHub OIDC provider + deploy role | They authorise the thing that runs Terraform. Managing them from inside Terraform means one bad apply locks CI out of the account. |
| IAM Identity Center | It is how the account is signed into at all, and it outlives every instance. |
| The $5 budget | It is the tripwire that proves the account is at $0.00. It must survive a `terraform destroy`. |

All four are recorded in [docs/RESOURCES.md](../docs/RESOURCES.md) with their teardown.

## Decisions worth knowing

**Directories, not workspaces.** Workspaces share one backend key and one state
file, and `terraform apply` in the wrong workspace is silent. A directory per
instance makes the target explicit, and dev and prod can diverge.

**The zip is built at plan time** from `src/`, by listing `**/*.py` explicitly
rather than zipping the directory. That keeps `__pycache__` out without relying
on the archive provider's exclude-glob behaviour, and it means editing a `.py`
file shows up as a Lambda update on the next plan. There is no build step and no
artefact to keep in sync.

**The log group is declared, not left to Lambda.** Lambda creates
`/aws/lambda/<function>` on first invocation with retention set to Never Expire,
and it survives the function's deletion — the leftover people
forget. Declared here, it has a retention and
`terraform destroy` actually removes it.

**No password touches the state.** Terraform creates the Cognito pool but not the
one user in it, because `aws_cognito_user` puts a temporary password in plain
text in the state file. Creating that user is a console step.

**The frontend and auth modules point at each other.** Cognito's callback URL
needs the CloudFront domain; the generated `config.js` needs Cognito's client id.
That is not a cycle — Terraform's graph is built from resources, not module
boundaries, and the two edges land on different resources. Verified: the graph
builds and reaches the first API call.

## The one local gotcha

On this machine Terraform cannot talk to its own provider plugins:

```
Failed to load plugin schemas ...
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

Terraform and its providers speak gRPC over `127.0.0.1` with a mutual-TLS
handshake, and an antivirus that inspects local connections intercepts it. It is not a
problem with the configuration. Two fixes, in order of preference:

1. Add an antivirus exclusion for `terraform.exe` and its `.terraform/providers`
   directory.
2. `TF_DISABLE_PLUGIN_TLS=1` in front of the command. It disables encryption on a
   loopback connection between two processes you already trust on your own
   desktop — acceptable here, but it is a workaround, not the fix.
