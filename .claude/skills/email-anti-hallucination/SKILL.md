---
name: email-anti-hallucination
description: >
  Protect and extend the three-layer email anti-hallucination guards that stop
  Aria from inventing a customer email and mailing a stranger. Use whenever
  editing request_image_upload, email validators, the email confirmation
  protocol in prompts, UploadService, or EmailService.
---

# Email anti-hallucination (do not weaken)

Highest-risk failure mode: the LLM invents an email from the caller's name
(e.g. "Ned Hassan" → `ned.hassan@gmail.com`) and SMTP sends an upload link to
a stranger.

Three intentional layers — keep all three. Never collapse to "just the prompt".

## Layer 1 — Prompt protocol (`app/agents/prompts.py`)

Ask → read back letter-by-letter → wait for explicit confirmation → only then
call `request_image_upload` with `customer_confirmed_aloud=true`.

Prompt-only guards get ignored under pressure. Always pair protocol text with
handler enforcement.

## Layer 2 — Schema validators (`app/agents/schemas.py`)

- Reuse `_reject_placeholder_email` on every email field.
- Block RFC-2606 / fabricated domains (`example.com`, `test.com`, …).
- Field `description=` must tell the model not to invent or construct from name.

## Layer 3 — Runtime gates (`handle_request_image_upload` in `tools.py`)

1. `customer_confirmed_aloud` must be True — otherwise return
   `status: needs_confirmation` with guidance (no DB / SMTP side effects).
2. `_looks_name_derived(email, customer_name)` — if local-part contains both
   first and last name fragments, refuse and ask the customer to spell it.

Guards run **before** `UploadService.issue_link` / `EmailService.send_upload_link`.

## When changing this area

- Prefer tightening (more domains, stronger heuristic) over loosening.
- If you must change behaviour, update prompt + schema + handler together.
- Smoke: text agent path that tries a name-derived email must get
  `needs_confirmation`, not an SMTP send.
