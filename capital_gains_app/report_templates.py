from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReportTemplate:
    name: str
    broker: str
    field_map: dict[str, str]
    created_at: str


def default_templates_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "CapitalGains" / "report_templates.json"


def load_report_templates(path: Path | None = None) -> list[ReportTemplate]:
    store = path or default_templates_path()
    if not store.exists():
        return []
    try:
        payload = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    templates: list[ReportTemplate] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        field_map = item.get("field_map", {})
        if not isinstance(field_map, dict):
            continue
        templates.append(
            ReportTemplate(
                name=str(item.get("name", "")).strip() or "Generic template",
                broker=str(item.get("broker", "generic")).strip() or "generic",
                field_map={str(key): str(value) for key, value in field_map.items() if value},
                created_at=str(item.get("created_at", "")).strip(),
            )
        )
    return templates


def save_report_template(template: ReportTemplate, path: Path | None = None) -> None:
    store = path or default_templates_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    templates = load_report_templates(store)

    normalized_new = _normalized_signature(template.field_map)
    filtered = [existing for existing in templates if _normalized_signature(existing.field_map) != normalized_new]
    filtered.append(template)

    serializable = [asdict(item) for item in filtered]
    store.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def build_report_template(name: str, field_map: dict[str, str], broker: str = "generic") -> ReportTemplate:
    return ReportTemplate(
        name=name.strip() or "Generic template",
        broker=broker.strip() or "generic",
        field_map={key: value for key, value in field_map.items() if value},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _normalized_signature(field_map: dict[str, str]) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for field_name, header_name in field_map.items():
        header = " ".join(str(header_name).strip().lower().split())
        normalized.append((str(field_name).strip().lower(), header))
    return tuple(sorted(normalized))
