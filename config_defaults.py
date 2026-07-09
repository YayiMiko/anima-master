from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RESET_TO_DEFAULTS_KEY = "reset_to_defaults"


def flatten_config(config: Any) -> dict[str, Any]:
    """Return a flat config dict from either legacy flat or grouped config."""
    source = dict(config or {})
    flat: dict[str, Any] = {}
    for key, value in source.items():
        if _is_config_group(key, value):
            flat.update(value)
    for key, value in source.items():
        if not _is_config_group(key, value):
            flat[key] = value
    return flat


def group_config(config: Any, schema_path: Path) -> dict[str, Any]:
    """Return config values grouped according to the current schema."""
    flat = flatten_config(config)
    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    grouped: dict[str, Any] = {}
    used: set[str] = set()
    for group_key, group_meta in schema.items():
        if not isinstance(group_meta, dict) or group_meta.get("type") != "object":
            continue
        items = group_meta.get("items")
        if not isinstance(items, dict):
            continue
        group_values: dict[str, Any] = {}
        for item_key in items:
            if item_key in flat:
                group_values[item_key] = flat[item_key]
                used.add(item_key)
            else:
                group_values[item_key] = _default_for_item(items[item_key])
        grouped[group_key] = group_values
    for key, value in flat.items():
        if key not in used:
            grouped[key] = value
    return grouped


def maybe_migrate_to_grouped_config(config: Any, schema_path: Path) -> dict[str, Any]:
    """Persist grouped config when the current config still uses flat keys."""
    current = dict(config or {})
    flat = flatten_config(current)
    grouped = group_config(flat, schema_path)
    if current != grouped and hasattr(config, "save_config"):
        config.save_config(replace_config=grouped)
    return grouped


def persist_flat_config_key(config: Any, schema_path: Path, key: str, value: Any) -> None:
    """Persist a flat config key into the grouped config store."""
    if not isinstance(config, dict):
        return
    grouped = group_config(config, schema_path)
    written = False
    for group_values in grouped.values():
        if isinstance(group_values, dict) and key in group_values:
            group_values[key] = value
            written = True
            break
    if not written:
        grouped[key] = value
    config.clear()
    config.update(grouped)


def schema_defaults(schema_path: Path) -> dict[str, Any]:
    """Return plugin config defaults parsed from _conf_schema.json."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    defaults: dict[str, Any] = {}
    for key, item in schema.items():
        defaults[key] = _default_for_item(item)
    return defaults


def maybe_reset_to_defaults(config: Any, schema_path: Path) -> dict[str, Any]:
    """Persist and return schema defaults when the reset switch is enabled."""
    current = flatten_config(config or {})
    if not bool(current.get(RESET_TO_DEFAULTS_KEY, False)):
        return flatten_config(config or {})

    defaults = schema_defaults(schema_path)
    grouped_defaults = group_config(defaults, schema_path)
    for group_values in grouped_defaults.values():
        if isinstance(group_values, dict) and RESET_TO_DEFAULTS_KEY in group_values:
            group_values[RESET_TO_DEFAULTS_KEY] = False
    if hasattr(config, "save_config"):
        config.save_config(replace_config=grouped_defaults)
    return flatten_config(grouped_defaults)


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
        items = item.get("items")
        if isinstance(items, dict):
            return {key: _default_for_item(value) for key, value in items.items()}
        return {}
    return ""


def _is_config_group(key: str, value: Any) -> bool:
    return str(key).startswith("anima_master_") and isinstance(value, dict)
