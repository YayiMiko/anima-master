from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


def run_cli_action(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run a CLI command body and convert exceptions to the legacy JSON shape."""
    try:
        return action()
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except TimeoutError as exc:
        return {"ok": False, "error": str(exc)}
    except requests.HTTPError as exc:
        response = exc.response
        body = response.text[:2000] if response is not None else str(exc)
        return {
            "ok": False,
            "error": "http_error",
            "status_code": response.status_code if response is not None else None,
            "body": body,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
