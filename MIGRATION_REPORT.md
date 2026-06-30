# Resin Society AI Chat Migration Report

Date: 2026-06-28

## Summary

Created a standalone Resin Society AI chat system from the GREET AI chat architecture without modifying GREET. The new system lives in:

`C:\Users\bgmss\Documents\Codex\2026-06-27\yes-this-is-the-next-correct\outputs\resin-society-ai-chatbox`

The system defaults to safe test mode. Chatwoot replies/support cases are dry-run unless explicitly enabled with production env variables.

## GREET Source Located

Source app found at:

`C:\Users\bgmss\OneDrive\Desktop\GREET AI CHATBOX`

Key GREET files copied as source architecture:

- `app.py`
- `openai_agent.py`
- `shopify_tools.py`
- `store_intelligence.py`
- `knowledge_tools.py`
- `blog_tools.py`
- `chatwoot_tools.py`
- `learning_tools.py`
- `memory_tools.py`
- `policy_tools.py`
- `ai_router.py`
- `intent_tools.py`
- `requirements.txt`
- `Procfile`

Not copied:

- GREET `.env`
- GREET virtualenvs
- GREET `greet_learning.db`
- GREET caches / `__pycache__`
- GREET test result artifacts
- GREET customer data

## Files Changed For Resin Society

- `app.py`: replaced GREET app logic with Resin Society FastAPI app, safe mode, lead capture, Resin escalation rules, Resin Chatwoot inbox guard, `/ai/ask`, `/ai/search`, `/chatwoot/webhook`, `/reports/summary`.
- `openai_agent.py`: replaced GREET dog prompt with Resin Society epoxy/project/supplier/product concierge prompt and Resin-specific tool contract.
- `policy_tools.py`: replaced GREET policy truth layer with Resin Society shipping, returns, order, contact, custom table, flooring, and trust guidance.
- `chatwoot_tools.py`: changed labels/custom attributes/private notes to `resin_*`; added dry-run behavior controlled by `RESIN_SAFE_TEST_MODE` and `RESIN_ENABLE_CHATWOOT_SEND`.
- `learning_tools.py`: added Resin-prefixed logging tables, lead table, unresolved question fields, daily/weekly summary support.
- `store_intelligence.py`: replaced dog product ranking with resin/project ranking for epoxy, deep pour, tabletop, river table, flooring, pigments, molds, sanding/polishing, woodworking tools.
- `knowledge_tools.py`: replaced dog article aliases with resin/project aliases.
- `blog_tools.py`: replaced dog article search routing with resin/project routing.
- `ai_router.py` and `intent_tools.py`: replaced dog routing with Resin Society routing.
- `shopify_tools.py`: supports `RESIN_SHOPIFY_STORE_DOMAIN` and `RESIN_SHOPIFY_ADMIN_ACCESS_TOKEN` while retaining generic fallbacks for isolated deployments.
- `.env.example`: added Resin-only env template.
- `README.md`: added local runbook, launch gate, deployment steps.
- `smoke_tests.py`: added safe offline smoke tests.

## Env Variables Needed

Required for live Resin deployment:

- `RESIN_SAFE_TEST_MODE=false` only after approval
- `RESIN_ENABLE_CHATWOOT_SEND=true` only after approval
- `RESIN_SHOPIFY_STORE_DOMAIN`
- `RESIN_SHOPIFY_ADMIN_ACCESS_TOKEN`
- `SHOPIFY_API_VERSION`
- `OPENAI_API_KEY`
- `OPENAI_AGENT_MODEL`
- `CHATWOOT_BASE_URL`
- `CHATWOOT_ACCOUNT_ID`
- `CHATWOOT_API_TOKEN`
- `RESIN_CHATWOOT_INBOX_ID`
- `RESIN_CHATWOOT_WEBSITE_TOKEN`
- `RESIN_CHATWOOT_WEBHOOK_SECRET`
- `RESIN_DATABASE_URL`
- `RESIN_DB_TABLE_PREFIX=resin`
- `RESIN_SUPPORT_EMAIL`
- `RESIN_TARGET_RESPONSE_SECONDS`
- `RESIN_CHAT_WORKERS`

## Chatwoot Setup Needed

Use the same Chatwoot account if desired, but create a new Website Inbox / Website Channel:

Recommended name: `Resin Society Website Chat`

Do not reuse:

- `GREET Dog Website Chat`
- GREET website token
- GREET inbox/channel ID
- GREET labels as primary routing labels

After creation:

1. Save the Resin website token as `RESIN_CHATWOOT_WEBSITE_TOKEN`.
2. Save the Resin inbox ID as `RESIN_CHATWOOT_INBOX_ID`.
3. Configure webhook URL to the Resin deployment: `https://<deployment-domain>/chatwoot/webhook`.
4. Keep `RESIN_SAFE_TEST_MODE=true` until manual approval.

## Conversation/Data Separation

The Resin app separates from GREET by:

- New folder.
- New env file.
- New deployment name.
- New Resin Shopify Admin API token.
- New Chatwoot website inbox/channel.
- `RESIN_CHATWOOT_INBOX_ID` guard in webhook.
- New Resin database URL recommended.
- Resin-prefixed tables: `resin_conversation_logs`, `resin_leads`, `resin_learning_events`.
- Resin-prefixed Chatwoot custom attributes and labels.
- Resin conversation IDs prefixed with `resin_embedded_` for embedded chat.

## Test Results

Commands run:

```powershell
python -m py_compile app.py openai_agent.py policy_tools.py chatwoot_tools.py learning_tools.py shopify_tools.py store_intelligence.py knowledge_tools.py blog_tools.py ai_router.py intent_tools.py memory_tools.py smoke_tests.py
python smoke_tests.py
```

Results:

- Python compile passed.
- Smoke test passed in safe mode.
- Resin quantity question returned sizing guidance.
- Order status without order/email asked for order number and checkout email.
- Custom table quote captured lead type, email, project size, and budget mention.
- Damaged order triggered follow-up/escalation behavior in safe mode.
- Chatwoot send remained disabled/dry-run.
- Shopify live product search was not tested because live Resin Shopify env credentials were not provided in this folder.
- Database logging was stubbed in smoke tests to avoid requiring live `RESIN_DATABASE_URL`.

## What Is Ready

- Standalone Resin backend source.
- Safe local test mode.
- Resin assistant prompt.
- Resin product/project intent routing.
- Resin lead capture fields.
- Resin escalation rules.
- Resin Chatwoot labels/custom attributes.
- Resin database table names.
- Summary report endpoint.
- Local smoke tests.
- Deployment Procfile.
- Env template.

## Manual Setup Still Needed

- Create new Chatwoot Resin Society website inbox/channel.
- Add Resin Chatwoot token/inbox ID to env.
- Add Resin Shopify Admin API token to env.
- Add Resin database URL to env.
- Verify Shopify product search with live Resin credentials.
- Verify Shopify order lookup with live Resin credentials.
- Install Resin widget/snippet on `resinsociety.net` only after approval.
- Decide production host/deployment service.

## Exact Local Command

```powershell
cd C:\Users\bgmss\Documents\Codex\2026-06-27\yes-this-is-the-next-correct\outputs\resin-society-ai-chatbox
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app:app --host 127.0.0.1 --port 5055 --reload
```

Smoke test:

```powershell
python smoke_tests.py
```

## Exact Deployment Steps

1. Create deployment app/service named `resin-society-ai-chatbox`.
2. Deploy contents of this folder.
3. Set Procfile command: `web: uvicorn app:app --host 0.0.0.0 --port $PORT`.
4. Add env variables from `.env.example` with Resin-only values.
5. Keep `RESIN_SAFE_TEST_MODE=true` and `RESIN_ENABLE_CHATWOOT_SEND=false` for first deploy.
6. Run `/` health check.
7. Run `POST /ai/ask` with sample Resin questions.
8. Verify live Shopify product search/order lookup.
9. Create and connect new Chatwoot Resin Society website inbox/channel.
10. Set Chatwoot webhook to `/chatwoot/webhook`.
11. Test Chatwoot webhook while safe mode is still on.
12. After approval, set `RESIN_SAFE_TEST_MODE=false` and `RESIN_ENABLE_CHATWOOT_SEND=true`.
13. Install the Resin website widget/snippet on `resinsociety.net`.

## Sample Questions For Approval Testing

- `How much resin do I need for a 72 x 30 x 2 inch river table?`
- `What deep pour epoxy should I use for a river table?`
- `Do you have mica powders for blue ocean resin?`
- `Where is my order #1234? My email is customer@example.com`
- `My order arrived damaged.`
- `I need a custom table quote for an 8 x 3 ft dining table, budget around $3000.`
- `I am a flooring contractor and need a quote for 1200 sq ft.`

## Risk Controls

- GREET source was not edited.
- GREET env and database were not copied.
- Resin defaults to safe mode.
- Chatwoot sends require two env switches.
- Webhook can reject non-Resin inbox traffic using `RESIN_CHATWOOT_INBOX_ID`.
- Database tables are Resin-prefixed by default.
