# Hosting the page on Amplify, by hand

The page is the one piece of this app still served from the developer's machine.
CloudFront, the usual way to put it on HTTPS, is refused by an account
verification that support had not lifted when this was written; the console
refuses identically.

Amplify Hosting is the cheapest thing to try: a static site over HTTPS, uploaded
as a zip, no repository, no build step. **It runs on CloudFront underneath, so
the same verification may refuse it.** Fifteen minutes tells us, and a second
refusal is a better thing to quote at support than the first.

Nothing here has been done. The resource list gets its entry when it is
done, with the teardown at the foot of this file.

## What it will serve

`dist/amplify-site.zip`, built by the snippet at the end of this file. Three
files at the TOP level of the zip (not inside a folder):

| file | what it is |
| --- | --- |
| `index.html` | the app |
| `guide.html` | the manual the `?` link opens |
| `config.js` | the three endpoints of the **hand-built** instance |

The page computes its own login redirect from wherever it is served, so the only
thing that has to change in AWS is the list of URLs Cognito and the API accept.

## 1. Upload it

1. Console → **Amplify**. Make sure the region reads **eu-central-1
   (Frankfurt)**, the region everything else is in. Hosting itself is global,
   but the app is created in the region you are looking at.
2. **Create new app** (upper right).
3. **Deploy without Git** → **Next**.
4. **App name**: `budget-tracker-page`.
5. **Branch name**: `manual`. This becomes part of the address, so a name you
   can read is worth having.
6. **Method**: **Drag and drop** → **Choose .zip folder** →
   `<repo>\dist\amplify-site.zip`.
7. **Save and deploy**.

It takes under a minute. The app page then shows the address:

```
https://manual.<app id>.amplifyapp.com
```

**If this is where it refuses** — anything about the account needing
verification before adding CloudFront resources, or a deployment that fails with
a permissions error naming CloudFront — stop and copy the message exactly. That
message is the next thing to send support, and the next option down the list
(API Gateway in front of the bucket) needs no CloudFront at all.

## 2. Let Cognito send the user back to it

The page is now at a new origin, and Cognito refuses any callback it has not
been told about. **Hand-built pool**, the one whose id is `<region>_<pool-id>`. The
console shows it as **"User pool - <suffix>"**: that is the name it gives a pool created
without one.

1. Console → **Cognito** → **User pools** → the pool with that id.
2. In the pool's left-hand menu, **Applications** → **App clients** → the
   client `<app-client-id>`. (There is no **App integration** tab any
   more; the console was reorganised and app clients moved here.)
3. On the client's page, **Login pages** → **Edit**. Older consoles called this
   section Hosted UI; newer ones, managed login pages.
4. **Allowed callback URLs**: add `https://manual.<app id>.amplifyapp.com/`
   — the **trailing slash matters**; the page asks for `origin + "/"`.
5. **Allowed sign-out URLs**: add the same address, slash included.
6. **Save changes**. Leave `http://localhost:5173/` in the list: that is how the
   page is served from the machine, and both can stay.

## 3. Let the API answer it

The API allows one origin at a time to call it from a browser. **Hand-built
API** (`budget-tracker-api`, id `<api-id>`):

1. Console → **API Gateway** → `budget-tracker-api` → **CORS**.
2. **Access-Control-Allow-Origin**: add `https://manual.<app id>.amplifyapp.com`
   — **no trailing slash** here. An origin never has a path.
3. Leave the rest as it is: `authorization, content-type` headers, `POST` and
   `OPTIONS` methods.
4. **Save**.

Nothing else changes. `POST /api` keeps its JWT authorizer: the three files
Amplify serves are public, the data is not, which is already true of the page on
the machine.

## 4. Check it

1. Open `https://manual.<app id>.amplifyapp.com` in a private window.
2. It should send you to the Cognito login page, take the password and the
   authenticator code, and come back to the app with the months in it.
3. Open the `?` in the header: the guide should open from the same address.
4. Add nothing yet. Compare one month's Total against the same month on
   `http://localhost:5173/`. Same figures means the hosted page is talking to
   the same instance, which is the whole point.

## 5. Optional: a password in front of it

Amplify can ask for a user name and password before it serves anything, which
is a second lock in front of the app's own:

Amplify → the app → **Hosting** → **Access control** → the `manual` branch →
**Restricted - password required** → set a user name and password → **Save**.

It protects the FILES, not the data; the data is behind Cognito either way.
Worth having if the thought of the page being fetchable by anyone bothers you.

## What it costs

Amplify Hosting's free tier covers 5 GB stored, 15 GB served a month and 1,000
build minutes; this is 200 KB of files, no build, and one reader. Past the free
tier it is cents. Nothing here idles at a cost.

## Teardown

For the resource list when it is done:

```
a) Console -> Amplify -> budget-tracker-page -> App settings -> General
   -> Delete app -> type the app name. That removes the branch, the files
   and the address.
b) Console -> Cognito -> User pools -> <region>_<pool-id> -> Applications ->
   App clients -> <app-client-id> -> Login pages -> Edit:
   remove the amplifyapp.com callback and sign-out URLs.
c) Console -> API Gateway -> budget-tracker-api -> CORS: remove the
   amplifyapp.com origin.
```

Deleting the Amplify app does not touch the data, the pool, the API or the
Lambda. After the teardown the page is served from the machine again, exactly as
before.

## Rebuilding the zip

Whenever `web/index.html` or `web/guide.html` changes, upload a new zip:
Amplify → the app → the `manual` branch → **Deploy updates** → drag the new zip.

```python
import pathlib, zipfile
root = pathlib.Path("<repo>")
with zipfile.ZipFile(root / "dist/amplify-site.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for name in ("index.html", "guide.html", "config.js"):
        z.write(root / "web" / name, name)      # config.js: the instance it talks to
```

`web/config.js` is not in the repository: copy `web/config.example.js` to it
and write in the three values of the instance this hosted copy should talk to
before building the zip.
