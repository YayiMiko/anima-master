from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LLMToolBridge:
    """Bridge AstrBot LLM tool methods to Anima plugin services."""

    def __init__(
        self,
        *,
        run_tool: Callable[[list[str]], Any],
        generate: Callable[..., Any],
        edit: Callable[[Any, str], Any],
        remove_bg: Callable[[Any], Any],
        spell: Callable[[Any], Any],
        reverse: Callable[[Any], Any],
    ):
        """Store callbacks used by decorated LLM tool entry points.

        Args:
            run_tool: Main ComfyUI helper runner.
            generate: Text-to-image generation callback.
            edit: Image edit callback.
            remove_bg: Background removal callback.
            spell: Embedded generation metadata extraction callback.
            reverse: Vision-based prompt reverse callback.
        """
        self._run_tool = run_tool
        self._generate = generate
        self._edit = edit
        self._remove_bg = remove_bg
        self._spell = spell
        self._reverse = reverse

    def capability_names(self) -> set[str]:
        """Return the stable capability names implemented by this bridge."""
        return {"status", "generate", "edit", "upscale", "remove_bg", "spell", "reverse"}

    async def status(self, event: Any) -> str:
        """Return a compact status string for LLM tool use.

        Args:
            event: AstrBot message event.

        Returns:
            Compact English status text for the model.
        """
        payload = await self._run_tool(["status"])
        if not payload.get("ok"):
            return f"ComfyUI status failed: {payload.get('error')}"
        return (
            "ComfyUI status: "
            f"base_url={payload.get('base_url')}, "
            f"workflow={payload.get('workflow')}, "
            f"allowed_sizes={payload.get('allowed_sizes')}, "
            f"version={payload.get('comfyui_version')}, "
            f"gpu={payload.get('gpu')}, "
            f"vram_free_mb={payload.get('vram_free_mb')}, "
            f"unet_available={payload.get('unet_available')}, "
            f"clip_available={payload.get('clip_available')}, "
            f"vae_available={payload.get('vae_available')}"
        )

    async def generate(
        self,
        event: Any,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        negative_prompt: str | None = None,
    ) -> str:
        """Generate an image via the plugin generation flow.

        Args:
            event: AstrBot message event.
            prompt: Prompt or tags to generate from.
            width: Optional width override.
            height: Optional height override.
            steps: Optional steps override.
            cfg: Optional CFG override.
            negative_prompt: Optional negative prompt override.

        Returns:
            Generation result summary.
        """
        return await self._generate(
            event,
            prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            negative_prompt=negative_prompt,
        )

    async def edit(self, event: Any, prompt: str) -> str:
        """Edit the most recent or quoted image.

        Args:
            event: AstrBot message event.
            prompt: Edit prompt.

        Returns:
            Edit result summary.
        """
        return await self._edit(event, prompt)

    async def remove_bg(self, event: Any) -> str:
        """Remove image background when the feature is enabled.

        Args:
            event: AstrBot message event.

        Returns:
            Background removal result summary.
        """
        return await self._remove_bg(event)

    async def extract_prompt(self, event: Any) -> str:
        """Extract embedded generation prompt metadata.

        Args:
            event: AstrBot message event.

        Returns:
            Extracted prompt information.
        """
        return await self._spell(event)

    async def reverse_prompt(self, event: Any) -> str:
        """Reverse-engineer prompt tags from the most recent or quoted image.

        Args:
            event: AstrBot message event.

        Returns:
            Reverse prompt tags or an error summary.
        """
        return await self._reverse(event)
