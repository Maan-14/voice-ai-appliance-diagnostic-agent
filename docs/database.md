# Database

Tables are created on startup via `init_db()` (`Base.metadata.create_all`).
Source of truth: `app/models/`.

## Overview

```
PostgreSQL / SQLite
        │
        ├── customers
        ├── technicians
        │     ├── service_areas
        │     ├── specialties
        │     └── availabilities
        ├── appointments
        ├── call_records
        ├── conversations (+ messages, tool events)
        └── upload_links
```

## Cascade rules (summary)

| If you delete… | Children |
|----------------|----------|
| a **customer** | `RESTRICT` — blocks delete if history exists |
| a **technician** | areas / specialties / availabilities `CASCADE`; appointments `RESTRICT` |
| an **availability** | appointment link set `NULL` |
| an **appointment** | call record appointment link set `NULL` |

`passive_deletes=True` is set on ORM relationships so the database
enforces cascades instead of SQLAlchemy emitting cascading DELETEs.

## Seed data

`python -m scripts.seed` inserts technicians, ZIP coverage, specialties,
and open availability slots. It is idempotent. Customers, appointments,
call records, uploads, and conversations are created by live traffic.

## Write flow (phone / agent)

1. **Call start** — in-memory `CallContextDTO` only (no DB row yet).
2. **Mid-call** — `update_call_context` / `record_diagnosis` update memory.
3. **Booking** — first major write: upsert customer by phone, insert
   appointment, mark availability booked.
4. **Image request** — upsert customer, insert `upload_links`, send email.
5. **Hangup** — insert `call_records` with transcript, diagnosis, outcome,
   and optional FKs to customer / appointment.

Web text and browser voice also persist to `conversations` /
`conversation_messages` through `ConversationRepository`, with AI titles
assigned via `title_service` when enough context exists.

## Resetting schema

`create_all` does not alter existing tables. After model changes:

```bash
python -m scripts.reset_db
python -m scripts.seed
```

Or for Docker Postgres volumes:

```bash
docker compose down -v
docker compose up --build
```
