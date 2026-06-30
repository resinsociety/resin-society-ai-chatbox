# Resin Society AI Chatbox

Standalone Resin Society migration of the GREET AI chat architecture. This folder is intentionally independent from GREET: separate env, separate Chatwoot inbox/channel, separate Shopify token, separate database/table prefix, and separate deployment name.

## Safe Local Run

```powershell
cd C:\Users\bgmss\Documents\Codex\2026-06-27\yes-this-is-the-next-correct\outputs\resin-society-ai-chatbox
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# fill Resin values, keep RESIN_SAFE_TEST_MODE=true
uvicorn app:app --host 127.0.0.1 --port 5055 --reload
```

Test:

```powershell
python smoke_tests.py
```

## Customer-Facing Launch Gate

Do not install on `resinsociety.net` until all are true:

- New Chatwoot website inbox/channel exists for Resin Society.
- `RESIN_CHATWOOT_INBOX_ID` and `RESIN_CHATWOOT_WEBSITE_TOKEN` are set from the Resin inbox only.
- Resin Shopify Admin token is verified.
- `RESIN_DATABASE_URL` points to a Resin-only database, or `RESIN_DB_TABLE_PREFIX=resin` is confirmed.
- Smoke tests pass.
- Manual approval is given.
- Only then set `RESIN_SAFE_TEST_MODE=false` and `RESIN_ENABLE_CHATWOOT_SEND=true` in production.

## Deployment

Suggested deployment name: `resin-society-ai-chatbox`.

Procfile command:

```text
web: uvicorn app:app --host 0.0.0.0 --port $PORT
```

Chatwoot webhook URL after deploy:

```text
https://<resin-chat-deployment-domain>/chatwoot/webhook
```

Embedded API endpoints:

```text
POST /ai/ask
POST /ai/search
GET /reports/summary?days=1
```
