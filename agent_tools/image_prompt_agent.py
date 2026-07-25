import argparse
import json
from pathlib import Path
from typing import Any

from comfyui_inputs import ComfyUIImageResolver
from image_metadata_reader import coerce_text, image_metadata, image_summary
from image_prompt_extractors import (
    extract_comfyui_graph,
    extract_json_generation,
    has_prompt_payload,
    json_loads_maybe,
    split_webui_parameters,
)


def _find_astrbot_root() -> Path:
    candidates = (Path.cwd().resolve(), *Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "astrbot").is_dir() and (candidate / "data").is_dir():
            return candidate
    return Path(__file__).resolve().parents[1]


ROOT = _find_astrbot_root()
WORKSPACE = ROOT / "workspace"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_RESOLVER = ComfyUIImageResolver(WORKSPACE, supported_exts=SUPPORTED_EXTS)


def _inside_workspace(path: Path) -> Path:
    return IMAGE_RESOLVER.inside_workspace(path)


def _path_from_record(record: dict[str, Any]) -> Path | None:
    return IMAGE_RESOLVER.path_from_record(record)


def _manifest_records() -> list[dict[str, Any]]:
    return IMAGE_RESOLVER.manifest_records()


def _latest_image() -> Path:
    return IMAGE_RESOLVER.latest_image()


def _resolve_input(value: str | None, *, allow_outside: bool = False) -> Path:
    value = str(value or "latest").strip()
    if not value or value.lower() == "latest":
        return IMAGE_RESOLVER.latest_image()
    if not allow_outside:
        return IMAGE_RESOLVER.resolve_image(value)
    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE / path
    if not path.exists() or not path.is_file():
        raise SystemExit(f"input image not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise SystemExit(f"unsupported image type: {path.suffix}")
    return path.resolve()


def _coerce_text(value: Any) -> str:
    return coerce_text(value)


def _json_loads_maybe(value: Any) -> Any:
    return json_loads_maybe(value)


def _extract_comfyui_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return extract_comfyui_graph(graph)


def _split_webui_parameters(text: str) -> dict[str, Any]:
    return split_webui_parameters(text)


def _extract_json_generation(data: dict[str, Any]) -> dict[str, Any]:
    return extract_json_generation(data)


def _has_prompt_payload(payload: dict[str, Any]) -> bool:
    return has_prompt_payload(payload)


def inspect_image(path: Path, *, include_raw: bool = False) -> dict[str, Any]:
    metadata = image_metadata(path)
    payload: dict[str, Any] = {"ok": True}
    payload.update(image_summary(path, WORKSPACE))
    payload.update(
        {
            "metadata_keys": sorted(metadata.keys()),
            "metadata_format": "",
            "positive_prompt": "",
            "negative_prompt": "",
            "parameters": {},
        }
    )

    for key in ("prompt", "workflow"):
        graph = _json_loads_maybe(metadata.get(key))
        if isinstance(graph, dict) and any(
            isinstance(v, dict) and "class_type" in v for v in graph.values()
        ):
            extracted = _extract_comfyui_graph(graph)
            payload.update(
                {
                    "metadata_format": extracted.get("format", ""),
                    "positive_prompt": extracted.get("positive_prompt", ""),
                    "negative_prompt": extracted.get("negative_prompt", ""),
                    "parameters": extracted.get("parameters", {}),
                }
            )
            if include_raw:
                payload["raw_metadata"] = metadata
            return payload

    for key in ("parameters", "Parameters"):
        if metadata.get(key):
            extracted = _split_webui_parameters(metadata[key])
            payload.update(
                {
                    "metadata_format": extracted.get("format", ""),
                    "positive_prompt": extracted.get("positive_prompt", ""),
                    "negative_prompt": extracted.get("negative_prompt", ""),
                    "parameters": extracted.get("parameters", {}),
                    "full_generation_info": extracted.get("full_generation_info", ""),
                }
            )
            if include_raw:
                payload["raw_metadata"] = metadata
            return payload

    for key in ("Comment", "comment", "Description", "generation_data"):
        data = _json_loads_maybe(metadata.get(key))
        if isinstance(data, dict):
            extracted = _extract_json_generation(data)
            if extracted:
                payload.update(
                    {
                        "metadata_format": extracted.get("format", ""),
                        "positive_prompt": extracted.get("positive_prompt", ""),
                        "negative_prompt": extracted.get("negative_prompt", ""),
                        "parameters": extracted.get("parameters", {}),
                        "full_generation_info": extracted.get(
                            "full_generation_info", {}
                        ),
                    }
                )
                if include_raw:
                    payload["raw_metadata"] = metadata
                return payload
        elif metadata.get(key):
            extracted = _split_webui_parameters(metadata[key])
            if extracted.get("positive_prompt"):
                payload.update(
                    {
                        "metadata_format": extracted.get("format", ""),
                        "positive_prompt": extracted.get("positive_prompt", ""),
                        "negative_prompt": extracted.get("negative_prompt", ""),
                        "parameters": extracted.get("parameters", {}),
                        "full_generation_info": extracted.get(
                            "full_generation_info", ""
                        ),
                    }
                )
                if include_raw:
                    payload["raw_metadata"] = metadata
                return payload

    if include_raw:
        payload["raw_metadata"] = metadata
    return payload


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_inspect(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    _print(inspect_image(path, include_raw=args.include_raw))


def cmd_positive(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    payload = inspect_image(path)
    _print(
        {
            "ok": True,
            "input": str(path),
            "metadata_format": payload.get("metadata_format", ""),
            "positive_prompt": payload.get("positive_prompt", ""),
        }
    )


def cmd_negative(args) -> None:
    path = _resolve_input(args.input, allow_outside=args.allow_outside)
    payload = inspect_image(path)
    _print(
        {
            "ok": True,
            "input": str(path),
            "metadata_format": payload.get("metadata_format", ""),
            "negative_prompt": payload.get("negative_prompt", ""),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="从图片元数据中提取生成提示词")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in (
        ("inspect", cmd_inspect),
        ("positive", cmd_positive),
        ("negative", cmd_negative),
    ):
        p = sub.add_parser(name)
        p.add_argument("--input", default="latest")
        p.add_argument("--allow-outside", action="store_true")
        if name == "inspect":
            p.add_argument("--include-raw", action="store_true")
        p.set_defaults(func=func)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
