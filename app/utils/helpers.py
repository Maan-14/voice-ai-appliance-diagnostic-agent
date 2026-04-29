"""Generic helpers — pure functions, no I/O."""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Iterator

import phonenumbers


# ---------- Tokens & codes ----------

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_confirmation_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------- Normalization ----------

_ZIP_RE = re.compile(r"\d{5}")


def normalize_zip(value: str | None) -> str | None:
    """Extract the first 5-digit US zip from a string."""
    if not value:
        return None
    m = _ZIP_RE.search(value)
    return m.group(0) if m else None


def normalize_phone(value: str | None, region: str = "US") -> str | None:
    """Return E.164 phone or None if unparseable."""
    if not value:
        return None
    try:
        parsed = phonenumbers.parse(value, region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        return None


_APPLIANCE_ALIASES = {
    "fridge": "refrigerator",
    "refrigerator": "refrigerator",
    "freezer": "refrigerator",
    "washer": "washer",
    "washing machine": "washer",
    "dryer": "dryer",
    "clothes dryer": "dryer",
    "dishwasher": "dishwasher",
    "oven": "oven",
    "stove": "oven",
    "range": "oven",
    "hvac": "hvac",
    "ac": "hvac",
    "air conditioner": "hvac",
    "furnace": "hvac",
    "heat pump": "hvac",
    "microwave": "microwave",
}


def normalize_appliance(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    if key in _APPLIANCE_ALIASES:
        return _APPLIANCE_ALIASES[key]
    for alias, canonical in _APPLIANCE_ALIASES.items():
        if alias in key:
            return canonical
    return None


# ---------- Time ----------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime; assume UTC if naive."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def iter_time_slots(
    start: datetime,
    end: datetime,
    duration_minutes: int = 60,
) -> Iterator[tuple[datetime, datetime]]:
    cursor = start
    delta = timedelta(minutes=duration_minutes)
    while cursor + delta <= end:
        yield cursor, cursor + delta
        cursor += delta
