# MarketUp Backend (FastAPI)

Real, tested backend — verified end-to-end in development (signup, login, JWT
refresh, business profile CRUD, AI content generation, post approve/reject all
confirmed working against a live server during development).

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set:
#   JWT_SECRET_KEY=<a long random string>
#   ANTHROPIC_API_KEY=<your Anthropic API key>        <-- optional if entered in the app
```

Get an Anthropic API key at https://console.anthropic.com if you don't have one.

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000/docs for interactive Swagger docs (auto-generated
by FastAPI) — you can test every endpoint from the browser.

Content generation is stateless: the app sends its locally saved business
profile and post options to `/ai/generate`, along with the key in the
`X-Api-Key` header. The API calls Anthropic and returns the generated post
without inserting it into a database; the app saves the returned post locally.
If the app has no API key configured, the server can use `ANTHROPIC_API_KEY`
from `.env`. No MongoDB configuration is used by this flow.
Anthropic returns an `image_prompt`, not image bytes or a URL, so this endpoint
leaves `generated_image` empty rather than substituting a preset photo. An
image-generation provider must be configured separately to return actual photos.

The Android emulator's default API URL (`http://10.0.2.2:8000/`) reaches this
computer's port 8000. Start the server before tapping **Generate Content**;
connection-refused errors mean no API server is listening at that address.

## Deploy for a release with Render

The repository includes a Render Blueprint in `render.yaml`. In Render, create
a new Blueprint from this repository and deploy the `marketup-api` web service.
After deployment, verify `https://<your-render-service>.onrender.com/health`
returns `{"status":"ok"}`. Use the exact HTTPS URL Render assigns when building
the release app:

```bash
./gradlew :app:bundleRelease \
  -PmarketupProductionApiBaseUrl=https://<your-render-service>.onrender.com/
```

The free Render plan can sleep when idle, so the first request may take longer
to start. Upgrade the service plan if release users need an always-on API.

For an Android physical device, use the computer's LAN IP (the device and
computer must be on the same network). Override the debug API address when
building with:

```bash
./gradlew :app:assembleDebug -PmarketupApiBaseUrl=http://<computer-lan-ip>:8000/
```

Keep the trailing slash. The Python server command above binds to `0.0.0.0`,
so it can accept connections from the device.

## Play Store release

A Play Store app must call a deployed API on a public HTTPS domain; a private
LAN address or `localhost` is not reachable by users. The release API URL is
intentionally unset in this project, and release builds fail until it is
provided:

```bash
./gradlew :app:bundleRelease \
  -PmarketupProductionApiBaseUrl=https://api.yourdomain.com/
```

You can provide the same value with the `MARKETUP_PRODUCTION_API_BASE_URL`
environment variable. Deploy the API first and verify its `/health` endpoint
is reachable over HTTPS.

The default SQLite database is suitable for local development; production
hosting needs persistent database storage. Also ensure the backend validates
the app's Cognito access tokens before relying on authenticated account data.

## What's real vs. stubbed

| Feature | Status |
|---|---|
| Signup / Login / JWT + refresh | ✅ Real, tested |
| Business profile CRUD | ✅ Real, tested |
| AI content generation (`/ai/generate`) | ✅ Stateless — calls Anthropic using the app's `X-Api-Key` or server `ANTHROPIC_API_KEY`, returns the post without saving it server-side. |
| Post approve/reject/list | Uses the app's local post store for generated content. |
| Database | SQLite remains for the separate account/business endpoints; content generation does not read or write it. No MongoDB is needed. |
| Instagram/Facebook/WhatsApp publishing | ❌ Not included in this pass — needs a Meta Developer App + long-lived tokens. See the full spec's §11 (Meta OAuth Integration Flow) for the exact flow to implement next. |
| Razorpay subscriptions | ❌ Not included in this pass — needs a live Razorpay account + Plan. See §16 of the spec. |

## Known gotcha already fixed for you

`passlib`'s bcrypt version-detection code breaks with modern `bcrypt` releases
(a known upstream issue). This project hashes passwords directly with the
`bcrypt` package instead of going through `passlib`, which avoids the bug
entirely — don't reintroduce `passlib` for auth.

## Next steps to make this production-grade

1. Swap SQLite → PostgreSQL (`DATABASE_URL=postgresql://user:pass@host/db`), add Alembic migrations.
2. Add the Meta OAuth + publishing routers (spec §11–13).
3. Add the Razorpay subscription routes + webhook handler (spec §15–16).
4. Move `JWT_SECRET_KEY` and `ANTHROPIC_API_KEY` into a real secrets manager before deploying.
