from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RESET_TO_DEFAULTS_KEY = "reset_to_defaults"


def schema_defaults(schema_path: Path) -> dict[str, Any]:
    """Return plugin config defaults parsed from _conf_schema.json."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    defaults: dict[str, Any] = {}
    for key, item in schema.items():
        defaults[key] = _default_for_item(item)
    return defaults


def maybe_reset_to_defaults(config: Any, schema_path: Path) -> dict[str, Any]:
    """Persist and return schema defaults when the reset switch is enabled."""
    current = dict(config or {})
    if not bool(current.get(RESET_TO_DEFAULTS_KEY, False)):
        return current

    defaults = schema_defaults(schema_path)
    defaults[RESET_TO_DEFAULTS_KEY] = False
    if hasattr(config, "save_config"):
        config.save_config(replace_config=defaults)
    return defaults


def _default_for_item(item: dict[str, Any]) -> Any:
    if "default" in item:
        return item["default"]
    item_type = item.get("type")
    if item_type == "bool":
        return False
    if item_type == "int":
        return 0
    if item_type == "float":
        return 0.0
    if item_type == "list":
        return []
    if item_type == "object":
        return {}
    return ""
