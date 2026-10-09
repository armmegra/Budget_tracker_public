# Serving the page from S3 through an API Gateway REST API, by hand

A second way to put the page on HTTPS inside AWS, built entirely in the console
and with no application code behind it. The page already has a home on Amplify
(see the other runbook), so **this is for the practice** and as a way round
Amplify should it ever be withdrawn. Both can run at once; both cost nothing
while nobody reads them.

What it teaches, which Amplify does not: a REST API's **AWS service
integration**, the IAM role an API assumes, path parameter mapping, response
header mapping, and stages.

Nothing here has been done. The resource list gets its entry when it works.

## Why a REST API and not the HTTP API we already have

Only a REST API can call an AWS service directly. An HTTP API (`budget-tracker
-api`, which serves the data) integrates with Lambda or with another HTTP
endpoint, not with S3. So this is a second, separate API whose only job is to
hand out three files.

## The one trap, already dealt with

A REST API serves everything under a **stage**: the page ends up at
`https://<api id>.execute-api.eu-central-1.amazonaws.com/prod/`. Until
an earlier fix the page asked Cognito to send it back to its origin plus a slash,
which there is the bare `execute-api` root. That routes nowhere and answers
`{"message":"Forbidden"}`. The page now asks to come back to the **directory it
was served from**, so under a stage it asks for `/prod/`. Nothing changed for
Amplify or for the local server.

**The files you upload to the bucket must be built from the current page**, or
the login will bounce to a Forbidden page.

## 1. A bucket of its own

Its own, rather than the data bucket (item 1) or the dev instance's web bucket:
those hold other things and the second belongs to Terraform.

1. Console → **S3** → **Create bucket**.
2. Name `budget-tracker-page-<account-id>` (bucket names are global; the account
   number keeps it unique, as the other buckets here do).
3. Region **eu-central-1**.
4. **Block all public access: leave it ON.** Nothing here is public; the API
   reads the bucket with a role, which is the whole point of the exercise.
5. Everything else default → **Create bucket**.
6. **Upload** the three files from `dist/amplify-site.zip` (unzip it first):
   `index.html`, `guide.html`, `config.js`. Upload them at the top level, not
   inside a folder.
7. Check their types afterwards: click `index.html` → **Properties** → the
   metadata should say `text/html`, and `config.js` should say
   `application/javascript` or `text/javascript`. The console sets these from
   the extension. If `config.js` came out as `application/octet-stream`, fix it
   with **Actions → Edit metadata**, or the browser will refuse to run it.

## 2. A role the API can assume to read that bucket

1. Console → **IAM** → **Roles** → **Create role**.
2. Trusted entity **AWS service**, use case **API Gateway** → **Next** →
   **Next**. (That use case attaches a logging policy and the trust policy; the
   read permission is added below.)
3. Name it `budget-tracker-page-reader` → **Create role**.
4. Open the role → **Add permissions** → **Create inline policy** → **JSON**,
   and paste exactly this, which allows reading those three objects and nothing
   else, in no other bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::budget-tracker-page-<account-id>/*"
  }]
}
```

5. Name it `read-the-page` → **Create policy**.
6. Copy the role's **ARN** from its summary page; the API asks for it.

## 3. The API

1. Console → **API Gateway** → **Create API** → **REST API** → **Build**.
   (Not "REST API Private", and not HTTP API.)
2. **New API**, name `budget-tracker-page`, endpoint type **Regional** →
   **Create API**.

### 3a. The page itself, at the stage root

1. With `/` selected, **Create method** → **GET**.
2. **Integration type**: **AWS service**.
3. **AWS Region** `eu-central-1`, **AWS service** `Simple Storage Service (S3)`,
   **HTTP method** `GET`, **Action type**: **Use path override**, and for
   **Path override** type:

   ```
   budget-tracker-page-<account-id>/index.html
   ```
4. **Execution role**: the ARN you copied.
5. **Create method**.

### 3b. Everything else, by file name

1. Select `/` → **Create resource**.
2. Leave the **Proxy resource** switch **off**. **Resource path** is a dropdown
   of PARENTS and offers only `/`: leave it. **Resource name** is the piece
   being added under that parent: type `{file}`, braces included. The braces
   make it a path parameter; without them the API answers only for a file
   literally called "file". (An older console had these two fields the other
   way round, which is how this step was first written.)
3. **Create resource**, then with `/{file}` selected → **Create method** →
   **GET**, the same integration as above, but **Path override**:

   ```
   budget-tracker-page-<account-id>/{key}
   ```
4. **Create method**.
5. Open the method's **Integration request** → **URL path parameters** →
   **Add path parameter**:

   | Name | Mapped from |
   | --- | --- |
   | `key` | `method.request.path.file` |

   That is the join: whatever follows the stage in the address becomes the
   object name S3 is asked for. The role allows nothing outside this bucket, so
   a clever reader can ask for other keys and get only 403s.

### 3c. Let the browser see the file's type

Without this, API Gateway answers everything as `application/json` and the
browser refuses to render the page or run the script.

For **each** of the two GET methods:

1. **Method response** → the `200` row → **Edit**. In the **Header name**
   section, which says "No response headers", press **Add header**, type
   `Content-Type`, then **Save**.
   Not the **Response body** section below it: its "Content type" and "Model"
   fields describe the body's shape for documentation, and **Add model** there
   only makes an empty row that refuses to save. Leave that section alone.
   This step DECLARES the header; the next one fills it.
2. **Integration response** → the `200` row → **Edit** → **Header mappings** →
   **Add header mapping**:

   | Response header | Mapped from |
   | --- | --- |
   | `Content-Type` | `integration.response.header.Content-Type` |

3. **Save**.

### 3d. Deploy

1. **Deploy API** → **New stage** → stage name `prod` → **Deploy**.
2. The **Invoke URL** appears at the top:
   `https://<api id>.execute-api.eu-central-1.amazonaws.com/prod`.
   **The address of the page is that plus a slash.**

A REST API, unlike an HTTP API, does not deploy itself. **Every later change
needs Deploy API again**, and forgetting is the classic hour lost here.

## 4. The two lists, as with Amplify

Same pool and same API as item 13, because this serves the same hand-built
instance.

**`<api id>` below is a placeholder, not text to paste.** Copy the **Invoke
URL** from the stage page instead and change only its end: it reads
`https://<rest-api-id>.execute-api.<region>.amazonaws.example/prod`, with no slash
after `prod`. Cognito wants it with a slash added; CORS wants it with `/prod`
cut off.

1. **Cognito** → **User pools** → `<region>_<pool-id>` ("User pool -
   <suffix>") → **Applications** → **App clients** → `<app-client-id>`
   → **Login pages** → **Edit**. Add to **both** lists, callback and sign-out:

   ```
   https://<api id>.execute-api.eu-central-1.amazonaws.com/prod/
   ```

   **With the stage and the trailing slash**, because that is the directory the
   page is served from and the page asks to come back to exactly it.
2. **API Gateway** → the HTTP API `budget-tracker-api` → **CORS** →
   **Access-Control-Allow-Origin**: add

   ```
   https://<api id>.execute-api.eu-central-1.amazonaws.com
   ```

   **No path, no slash** — an origin is scheme and host only. Remember to press
   **Add** so it becomes a chip before **Save**.

Leave every existing entry in both lists. Four addresses can serve this one
instance: localhost, Amplify, this, and the dev page's port 8000.

## 5. Check it

1. `https://<api id>.execute-api.eu-central-1.amazonaws.com/prod/` in a private
   window → the Cognito page → password → authenticator code → the months.
2. The `?` link: the guide opens at `.../prod/guide.html`.
3. A month's Total matches the same month on Amplify and on `localhost:5173`.

**If it does not work, in order of likelihood:**

| What you see | What it is |
| --- | --- |
| The page downloads instead of rendering | step 3c, the `Content-Type` mapping, on that method |
| `{"message":"Forbidden"}` after login | the callback URL is missing `/prod/` or its slash |
| `{"message":"Missing Authentication Token"}` | the address is missing the stage, or the change was never deployed |
| The page loads, every button fails | the CORS origin on `budget-tracker-api`, or it has a path or slash |
| `AccessDenied` as the page body | the role's policy, or a file that is not in that bucket |
| Changes that do nothing | **Deploy API** again |

## What it costs

REST API requests are $3.50 per million, S3 GETs $0.0004 per thousand, storage
on 200 KB is nothing. A page load is three requests. At one reader this rounds
to zero, but unlike Amplify's free tier it is **not** free by rule: it is free
because nobody reads it.

## Teardown

```
a) Console -> API Gateway -> APIs -> budget-tracker-page -> Actions ->
   Delete API (the stage and the methods go with it).
b) Console -> S3 -> budget-tracker-page-<account-id> -> Empty, then Delete.
c) Console -> IAM -> Roles -> budget-tracker-page-reader -> Delete
   (its inline policy goes with it).
d) Cognito -> the pool -> Applications -> App clients -> the client ->
   Login pages -> Edit: remove the execute-api callback and sign-out URLs.
e) API Gateway -> budget-tracker-api -> CORS: remove the execute-api origin.
```

None of that touches the data, the pool, the Lambda or the Amplify copy.
