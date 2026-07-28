from __future__ import annotations

from typing import Any


def parse_size(value: Any) -> tuple[int, int] | None:
    if isinstance(value, str):
        text = value.strip().lower()
        for separator in ("x", "×", "*", "＊", "✕", "✖", "х"):
            text = text.replace(separator, "x")
        if "x" not in text:
            return None
        left, right = text.split("x", 1)
        try:
            width = int(left.strip())
            height = int(right.strip())
        except ValueError:
            return None
        if width > 0 and height > 0:
            return width, height
    if isinstance(value, dict):
        try:
            width = int(value.get("width"))
            height = int(value.get("height"))
        except (TypeError, ValueError):
            return None
        if width > 0 and height > 0:
            return width, height
    return None


def allowed_sizes(
    config: dict[str, Any], default_sizes: list[str]
) -> list[tuple[int, int]]:
    raw_sizes = config.get("allowed_sizes") or default_sizes
    sizes: list[tuple[int, int]] = []
    for item in raw_sizes if isinstance(raw_sizes, list) else []:
        parsed = parse_size(item)
        if parsed and parsed not in sizes:
            sizes.append(parsed)
    if not sizes:
        sizes = [item for item in (parse_size(item) for item in default_sizes) if item]
    return sizes


def generation_size(
    config: dict[str, Any], default_sizes: list[str], width: int, height: int
) -> tuple[int, int]:
    width = int(width)
    height = int(height)
    allowed = allowed_sizes(config, default_sizes)
    if allowed and (width, height) not in allowed:
        requested_ratio = width / height
        same_orientation = [
            size for size in allowed if (size[0] >= size[1]) == (width >= height)
        ] or allowed
        width, height = min(
            same_orientation,
            key=lambda size: (
                abs((size[0] / size[1]) - requested_ratio),
                abs(size[0] * size[1] - width * height),
            ),
        )
    return width, height
