# Development

## Local run

See the [README Quick Start](../README.md#try-aria). Default database is
SQLite (`DATABASE_URL=sqlite+aiosqlite:///./data/voice_ai.db`).

## Docker (Postgres)

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` and switch `DATABASE_URL` to:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/voice_ai
```

Then:

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

## Environment variables

Loaded once via `get_settings()`. See [`.env.example`](../.env.example).

| Group | Keys |
|-------|------|
| App | `APP_NAME`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `APP_PUBLIC_URL`, `LOG_LEVEL` |
| Database | `DATABASE_URL`, `DATABASE_ECHO` |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_REALTIME_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_TITLE_MODEL`, `OPENAI_TTS_VOICE` |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS` |
| Upload | `UPLOAD_DIR`, `UPLOAD_LINK_TTL_HOURS`, `UPLOAD_MAX_BYTES` |
| Business | `BUSINESS_TIMEZONE`, `SUPPORTED_APPLIANCES` |

## Exposing to Twilio

```bash
ngrok http 8000
```

Set `APP_PUBLIC_URL` to the ngrok HTTPS URL. Point the Twilio number’s
voice webhook to:

```
POST https://<your-host>/voice/inbound
```

## Troubleshooting

### `audioop` missing on Python 3.13+

`requirements.txt` includes `audioop-lts` for Python ≥ 3.13. Rebuild the
venv if needed.

### Twilio `11200` retrieval failure

`APP_PUBLIC_URL` is not reachable from the public internet, or does not
match the Twilio console webhook.

### SQLite `database is locked`

Another process (second server, leftover client) is holding the DB.
Stop extra processes, or use the Docker Postgres stack for concurrent use.

### Stale schema after model changes

```bash
python -m scripts.reset_db
python -m scripts.seed
```

### Useful checks

```bash
pytest
python -c "from app.main import app; print(app.title)"
curl -s http://127.0.0.1:8000/health
```
