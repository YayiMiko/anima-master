from astrbot.api.star import Context, Star

try:
    from .entry_support import EntrySupportMixin
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from entry_support import EntrySupportMixin


class ComfyUIAgentPlugin(EntrySupportMixin, Star):
    """Basic local ComfyUI backend for AstrBot."""
    pass
