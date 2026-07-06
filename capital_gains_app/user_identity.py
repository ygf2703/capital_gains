from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


EMAIL_ENV = "CAPITAL_GAINS_USER_EMAIL"
NAME_ENV = "CAPITAL_GAINS_USER_NAME"


@dataclass(frozen=True, slots=True)
class UserIdentity:
    email: str = ""
    name: str = ""

    @property
    def display_name(self) -> str:
        return clean_display_name(self.name) or display_name_from_email(self.email)


def load_user_identity(profile_path: Path | None = None) -> UserIdentity:
    env_identity = UserIdentity(
        email=os.environ.get(EMAIL_ENV, "").strip(),
        name=os.environ.get(NAME_ENV, "").strip(),
    )
    if env_identity.email or env_identity.name:
        return env_identity

    path = profile_path or default_profile_path()
    if not path.exists():
        return UserIdentity()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UserIdentity()
    return UserIdentity(email=str(data.get("email", "")).strip(), name=str(data.get("name", "")).strip())


def default_profile_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "CapitalGains" / "profile.json"


def greeting_for_user(identity: UserIdentity) -> str:
    name = identity.display_name
    if name:
        return f"היי {name}, יש קבצים לניתוח?"
    return "היי, יש קבצים לניתוח?"


def clean_display_name(name: str) -> str:
    return " ".join(name.strip().split())


def display_name_from_email(email: str) -> str:
    local_part = email.strip().split("@", 1)[0]
    if not local_part:
        return ""
    local_part = local_part.split("+", 1)[0]
    tokens = [token for token in re.split(r"[._\-\s]+", local_part) if token]
    if not tokens:
        return ""
    first = tokens[0]
    if _has_hebrew(first):
        return first
    return first[:1].upper() + first[1:].lower()


def _has_hebrew(text: str) -> bool:
    return any("\u0590" <= char <= "\u05ff" for char in text)
