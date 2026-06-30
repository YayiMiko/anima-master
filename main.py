import asyncio
from datetime import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_root

try:
    from .danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )
    from .prompt_builder import (
        apply_config_preset,
        build_final_prompt,
        build_llm_prompt,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
        wants_default_character,
    )
except Exception:  # pragma: no cover - fallback for direct script-style imports.
    from danbooru_tags import (
        DEFAULT_DONMAI_BASE_URLS,
        DEFAULT_USER_AGENT,
        required_core_tags_for_prompt,
        resolve_core_tags,
    )
    from prompt_builder import (
        apply_config_preset,
        build_final_prompt,
        build_llm_prompt,
        selected_fixed_character,
        strip_raw_prefix,
        wants_sensual_mode,
        wants_default_character,
    )

try:
    from astrbot.core.tools.web_search_tools import _tavily_search
except Exception:  # pragma: no cover - web search internals may move upstream.
    _tavily_search = None

try:
    from aiocqhttp.exceptions import ActionFailed
except Exception:  # pragma: no cover - aiocqhttp may be absent in tests.
    ActionFailed = None

ROOT = Path(get_astrbot_root())
PLUGIN_DIR = Path(__file__).resolve().parent
TOOL = PLUGIN_DIR / "agent_tools" / "comfyui_agent.py"
PROMPT_TOOL = PLUGIN_DIR / "agent_tools" / "image_prompt_agent.py"
if not TOOL.exists():
    TOOL = ROOT / "agent_tools" / "comfyui_agent.py"
if not PROMPT_TOOL.exists():
    PROMPT_TOOL = ROOT / "agent_tools" / "image_prompt_agent.py"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
WORKSPACE = ROOT / "workspace"
INPUTS = WORKSPACE / "inputs"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
REFERENCE_PROMPT_MARKERS = (
    "参考引用图",
    "引用图",
    "参考这张图",
    "参考这图",
    "按这张图",
    "照这张图",
    "根据这张图",
    "用这张图",
    "以这张图",
    "参考图片",
    "参考图",
)
WEB_SEARCH_KEYWORDS = (
    "联网",
    "搜索",
    "搜一下",
    "查一下",
    "参考资料",
    "官方图",
    "设定图",
    "资料",
)
DEEP_THINKING_KEYWORDS = (
    "深度思考",
    "认真想",
    "仔细想",
    "严格还原",
    "高度还原",
    "不要跑偏",
    "核心特征",
)

_ROUTE_PREFIX_RE = re.compile(r"^\s*/?", re.IGNORECASE)
_SPACES_RE = re.compile(r"\s+")


class ComfyUIAgentPlugin(Star):
    """Basic local ComfyUI backend for AstrBot."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        self.config = apply_config_preset(dict(config or {}))
        self._startup_lock = asyncio.Lock()
        self._danbooru_tag_cache: dict[str, list[Any]] = {}

    async def initialize(self):
        img2img_enabled = self._bool("img2img_enabled", False)
        if img2img_enabled:
            edit_tool_changed = self.context.activate_llm_tool("comfyui_edit")
        else:
            edit_tool_changed = self.context.deactivate_llm_tool("comfyui_edit")
        logger.info(
            "[comfyui_agent] enabled=%s preset=%s img2img_enabled=%s edit_tool_changed=%s base_url=%s workflow=%s",
            self._bool("enabled", True),
            self._str("preset_profile", "none") or "none",
            img2img_enabled,
            edit_tool_changed,
            self._str("comfyui_base_url", "http://127.0.0.1:8188"),
            self._str("workflow", "anima_t2i"),
        )

    def _bool(self, key: str, default: bool) -> bool:
        return bool(self.config.get(key, default))

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _str(self, key: str, default: str = "") -> str:
        value = self.config.get(key, default)
        return str(value if value is not None else default)

    def _safe_name(self, value: str, fallback: str = "image") -> str:
        name = Path(str(value).replace("\\", "/")).name.strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = name.strip(" .")
        return name or fallback

    def _input_target_dir(self, event: AstrMessageEvent) -> Path:
        date_dir = datetime.now().strftime("%Y%m%d")
        session = self._safe_name(event.get_session_id() or "session", "session")
        target_dir = INPUTS / date_dir / session
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _write_input_record(self, event: AstrMessageEvent, target: Path, original: str) -> None:
        INPUTS.mkdir(parents=True, exist_ok=True)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "platform_id": event.get_platform_id(),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "kind": "image",
            "original_name": self._safe_name(original, "image"),
            "path": str(target),
            "relative_path": str(target.relative_to(WORKSPACE)),
            "size": target.stat().st_size,
            "source": "comfyui_hard_route",
        }
        manifest = INPUTS / "manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        (INPUTS / "latest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _save_image_component(
        self,
        event: AstrMessageEvent,
        component: Comp.Image,
        label: str,
        index: int,
    ) -> str | None:
        try:
            source = Path(await component.convert_to_file_path())
        except Exception as exc:
            logger.warning("[comfyui_agent] failed to resolve %s image: %s", label, exc)
            return None
        if not source.exists() or not source.is_file():
            logger.warning("[comfyui_agent] resolved %s image does not exist: %s", label, source)
            return None
        original = component.file or component.url or source.name or "image.png"
        ext = Path(str(original)).suffix.lower() or source.suffix.lower()
        if ext not in SUPPORTED_IMAGE_EXTS:
            ext = ".png"
        timestamp = datetime.now().strftime("%H%M%S%f")
        sender = self._safe_name(event.get_sender_id() or "unknown", "unknown")
        filename = f"{timestamp}_{sender}_{label}_image_{index}{ext}"
        target = self._input_target_dir(event) / filename
        shutil.copy2(source, target)
        self._write_input_record(event, target, original)
        logger.info("[comfyui_agent] saved %s image input: %s", label, target)
        return str(target)

    async def _event_image_input(self, event: AstrMessageEvent) -> str | None:
        direct_images: list[Comp.Image] = []
        reply_images: list[Comp.Image] = []
        for component in event.get_messages():
            if isinstance(component, Comp.Image):
                direct_images.append(component)
            elif isinstance(component, Comp.Reply):
                for inner in component.chain or []:
                    if isinstance(inner, Comp.Image):
                        reply_images.append(inner)

        # For quoted commands such as "/anm 抠图", the quoted image is the target.
        for index, image in enumerate(reply_images or direct_images, start=1):
            saved = await self._save_image_component(
                event,
                image,
                "reply" if reply_images else "message",
                index,
            )
            if saved:
                return saved
        return None

    def _is_allowed(self, event: AstrMessageEvent) -> bool:
        if not self._bool("enabled", True):
            return False
        if self._bool("admin_only", False) and not event.is_admin():
            return False
        allowed = self.config.get("allowed_sender_ids", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed_set = {str(item).strip() for item in allowed or [] if str(item).strip()}
        if allowed_set and str(event.get_sender_id()) not in allowed_set:
            return False
        return True

    def _is_auto_start_allowed(self, event: AstrMessageEvent) -> bool:
        if not self._bool("auto_start", False):
            return False
        allowed = self.config.get("auto_start_allowed_sender_ids", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed_set = {str(item).strip() for item in allowed or [] if str(item).strip()}
        if str(event.get_sender_id()) in allowed_set:
            return True
        if self._bool("auto_start_admin_only", True):
            return event.is_admin()
        return True

    def _help_text(self) -> str:
        lines = [
            "Anima 指令表：",
            "- /anm 帮助：查看这份指令表",
            "- /anm 状态：查看 ComfyUI / Anima 状态",
            "- /anm 生图 <描述>：按描述生成图片",
            "- /anm 原样 <tags>：跳过 LLM 优化，直接按 tags 生图",
        ]
        if self._bool("img2img_enabled", False):
            lines.append("- /anm 改图 <要求>：引用图片后整图重绘/风格化")
        lines.extend(
            [
                "- /anm 去背景：引用图片或使用最近图片抠图",
                "- /anm 解析法术：读取图片内嵌的生成信息",
                "- /anm 反推：根据图片内容反推 tags",
                "",
                "也可以把“anm”换成“comfyui / anima”。",
                "例：/anm 生图 白色礼服，立绘",
            ]
        )
        return "\n".join(lines)

    def _normalize_route_text(self, text: str) -> str:
        text = _ROUTE_PREFIX_RE.sub("", str(text or "")).strip()
        return _SPACES_RE.sub(" ", text)

    def _parse_hard_route(self, text: str) -> tuple[str, str] | None:
        normalized = self._normalize_route_text(text)
        lowered = normalized.lower()
        prefixes = ("anm", "comfyui", "anima")

        for prefix in prefixes:
            if not lowered.startswith(prefix.lower()):
                continue
            rest = normalized[len(prefix) :].strip(" ，,：:")
            if not rest:
                return "help", ""
            rest_lower = rest.lower()
            action_map = [
                ("help", "help"),
                ("帮助", "help"),
                ("指令表", "help"),
                ("指令", "help"),
                ("菜单", "help"),
                ("status", "status"),
                ('״̬', "status"),
                ("generate", "generate"),
                ("生图", "generate"),
                ("画图", "generate"),
                ("edit", "edit"),
                ("改图", "edit"),
                ("图生图", "edit"),
                ("风格化", "edit"),
                ("重绘", "edit"),
                ("upscale", "disabled_upscale"),
                ("放大", "disabled_upscale"),
                ("高清修复", "disabled_upscale"),
                ("高清", "disabled_upscale"),
                ("remove_bg", "remove_bg"),
                ("remove-bg", "remove_bg"),
                ("抠图", "remove_bg"),
                ("去背景", "remove_bg"),
                ("去除背景", "remove_bg"),
                ("解析法术", "spell"),
                ("法术解析", "spell"),
                ("读取法术", "spell"),
                ("提取提示词", "spell"),
                ("读取提示词", "spell"),
                ("反推提示词", "reverse"),
                ("图片反推", "reverse"),
                ("反推", "reverse"),
            ]
            for keyword, action in action_map:
                if not rest_lower.startswith(keyword.lower()):
                    continue
                prompt = rest[len(keyword) :].strip(" ，,：:")
                return action, prompt
            if prefix.lower() != "anm":
                return None
            return "generate", rest

        natural = re.match(
            r"^(?:用\s*)?(?:anm|comfyui|anima)"
            r"(?:帮我|给我|来)?"
            r"\s*"
            r"(帮助|指令表|指令|菜单|help|画一张|画个|画|生图|生成|改图|重绘|风格化|放大|高清修复|高清|抠图|去背景|去除背景|解析法术|法术解析|读取法术|提取提示词|读取提示词|反推提示词|图片反推|反推)"
            r"\s*(.*)$",
            normalized,
            flags=re.IGNORECASE,
        )
        if not natural:
            return None
        verb = natural.group(1)
        prompt = natural.group(2).strip(" ，,：:")
        if verb.lower() == "help" or verb in {"帮助", "指令表", "指令", "菜单"}:
            return "help", prompt
        if verb in {"改图", "重绘", "风格化"}:
            return "edit", prompt
        if verb in {"放大", "高清修复", "高清"}:
            return "disabled_upscale", prompt
        if verb in {"抠图", "去背景", "去除背景"}:
            return "remove_bg", prompt
        if verb in {"解析法术", "法术解析", "读取法术", "提取提示词", "读取提示词"}:
            return "spell", prompt
        if verb in {"反推提示词", "图片反推", "反推"}:
            return "reverse", prompt
        if verb in {"画一张", "画个", "画"}:
            prompt = f"{verb}{prompt}".strip()
        return "generate", prompt

    def _comfyui_ready(self, payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("ok")
            and payload.get("enabled", True)
            and payload.get("unet_available")
            and payload.get("clip_available")
            and payload.get("vae_available")
        )

    async def _run_python_tool(
        self, script: Path, args: list[str], timeout: int
    ) -> dict[str, Any]:
        python = str(PYTHON if PYTHON.exists() else Path(sys.executable))
        proc = await asyncio.create_subprocess_exec(
            python,
            str(script),
            *args,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"ok": False, "error": f"local_wait_timeout_after_{timeout}s"}

        out_text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()
        if not out_text:
            return {
                "ok": False,
                "error": "empty_tool_output",
                "stderr": err_text[-1200:],
                "returncode": proc.returncode,
            }
        try:
            payload = json.loads(out_text)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "invalid_tool_json",
                "stdout": out_text[-2000:],
                "stderr": err_text[-1200:],
                "returncode": proc.returncode,
            }
        if err_text:
            payload["stderr"] = err_text[-1200:]
        payload["returncode"] = proc.returncode
        return payload

    async def _run_tool(self, args: list[str]) -> dict[str, Any]:
        timeout = max(self._int("timeout", 900), 30) + 60
        return await self._run_python_tool(TOOL, args, timeout)

    async def _run_prompt_tool(self, args: list[str]) -> dict[str, Any]:
        return await self._run_python_tool(PROMPT_TOOL, args, 120)

    async def _current_chat_provider_id(self, event: AstrMessageEvent) -> str:
        configured = self._str("prompt_builder_provider_id", "").strip()
        if configured:
            return configured
        try:
            provider_id = await self.context.get_current_chat_provider_id(
                event.unified_msg_origin
            )
            return str(provider_id or "").strip()
        except Exception as exc:
            logger.warning("[comfyui_agent] failed to get current chat provider: %s", exc)
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        return str(cfg.get("provider_settings", {}).get("default_provider_id") or "").strip()

    async def _image_caption_provider_id(self, event: AstrMessageEvent) -> str:
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        return str(
            provider_settings.get("default_image_caption_provider_id")
            or provider_settings.get("default_provider_id")
            or ""
        ).strip()

    def _wants_reference_image(self, prompt: str) -> bool:
        text = str(prompt or "")
        return any(marker in text for marker in REFERENCE_PROMPT_MARKERS)

    def _shorten(self, text: str, limit: int = 1800) -> str:
        text = str(text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...[已截断]"

    def _format_spell_payload(self, payload: dict[str, Any]) -> str:
        if not payload.get("ok"):
            return f"法术解析失败：{payload.get('error') or 'unknown_error'}"
        positive = str(payload.get("positive_prompt") or "").strip()
        negative = str(payload.get("negative_prompt") or "").strip()
        params = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
        lines = [
            "法术解析结果：",
            f"- 格式：{payload.get('metadata_format') or '未识别到生成信息'}",
            f"- 尺寸：{payload.get('width')}x{payload.get('height')}",
        ]
        if params:
            compact_params = []
            for key in ("steps", "Steps", "cfg", "CFG scale", "sampler_name", "Sampler", "scheduler", "seed", "Seed", "size", "Size"):
                if key in params:
                    compact_params.append(f"{key}={params[key]}")
            if compact_params:
                lines.append(f"- 参数：{', '.join(compact_params)}")
        lines.append("")
        lines.append("正面提示词：")
        lines.append(self._shorten(positive or "未读取到正面提示词", 2200))
        if negative:
            lines.append("")
            lines.append("负面提示词：")
            lines.append(self._shorten(negative, 1000))
        return "\n".join(lines)

    async def _image_spell_payload(self, event: AstrMessageEvent, image_input: str | None = None) -> dict[str, Any]:
        image_input = image_input or await self._event_image_input(event)
        args = ["inspect"]
        if image_input:
            args.extend(["--input", image_input])
        else:
            args.extend(["--input", "latest"])
        return await self._run_prompt_tool(args)

    async def _reverse_image_tags(self, event: AstrMessageEvent, image_input: str | None = None) -> str:
        image_input = image_input or await self._event_image_input(event)
        if not image_input:
            image_input = "latest"
        provider_id = await self._image_caption_provider_id(event)
        if not provider_id:
            return ""
        prompt = (
            "请反推这张二次元图片的生图提示词。"
            "输出英文 danbooru tags，用英文逗号分隔；不要解释，不要 Markdown。"
            "优先描述主体、角色外观、服饰、动作、神态、构图、背景、画风和质量观感。"
            "不要臆造网页出处，不要输出中文。"
        )
        try:
            response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                image_urls=[image_input],
                max_tokens=self._int("prompt_builder_max_tokens", 700),
            )
            return str(getattr(response, "completion_text", "") or "").strip()
        except Exception as exc:
            logger.warning("[comfyui_agent] reverse image tags failed: %s", exc)
            return ""

    async def _reference_prompt_context(self, event: AstrMessageEvent, image_input: str) -> str:
        payload = await self._image_spell_payload(event, image_input)
        positive = str(payload.get("positive_prompt") or "").strip() if payload.get("ok") else ""
        if positive:
            return "参考图原始正面提示词：\n" + self._shorten(positive, 2200)
        reverse = await self._reverse_image_tags(event, image_input)
        if reverse:
            return "参考图视觉反推 tags：\n" + self._shorten(reverse, 1800)
        return ""

    async def _augment_prompt_with_reference_image(self, event: AstrMessageEvent, prompt: str) -> str | None:
        if not self._wants_reference_image(prompt):
            return prompt
        image_input = await self._event_image_input(event)
        if not image_input:
            logger.info("[comfyui_agent] reference image requested but no image component found")
            return None
        reference = await self._reference_prompt_context(event, image_input)
        if not reference:
            return prompt
        logger.info("[comfyui_agent] prompt augmented with image reference chars=%s", len(reference))
        return f"用户要求：{prompt}\n{reference}"

    def _prompt_search_query(self, prompt: str) -> str:
        template = self._str(
            "prompt_builder_search_query_template",
            "{prompt} anime game character outfit pose official art visual design",
        ).strip()
        if "{prompt}" in template:
            return template.replace("{prompt}", prompt).strip()
        return f"{prompt} {template}".strip()

    def _keyword_reason(self, prompt: str, keywords: tuple[str, ...]) -> str:
        text = str(prompt or "").lower()
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return ""

    async def _prompt_search_context(self, event: AstrMessageEvent, prompt: str) -> str:
        if not self._bool("prompt_builder_web_search_enabled", True):
            return ""
        if _tavily_search is None:
            logger.warning("[comfyui_agent] prompt web search unavailable: tavily helper missing")
            return ""

        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})
            if not provider_settings.get("websearch_tavily_key", []):
                logger.warning("[comfyui_agent] prompt web search skipped: Tavily key not configured")
                return ""
            max_results = max(1, min(self._int("prompt_builder_search_max_results", 5), 8))
            payload = {
                "query": self._prompt_search_query(prompt),
                "max_results": max_results,
                "include_favicon": False,
                "search_depth": self._str("prompt_builder_search_depth", "advanced") or "advanced",
                "topic": "general",
            }
            if payload["search_depth"] not in {"basic", "advanced"}:
                payload["search_depth"] = "advanced"
            results = await _tavily_search(provider_settings, payload)
        except Exception as exc:
            logger.warning("[comfyui_agent] prompt web search failed: %s", exc)
            return ""

        lines = [f"用户主题：{prompt}", "搜索结果："]
        for idx, result in enumerate(results, 1):
            title = str(getattr(result, "title", "") or "").strip()
            url = str(getattr(result, "url", "") or "").strip()
            snippet = str(getattr(result, "snippet", "") or "").strip()
            snippet = _SPACES_RE.sub(" ", snippet)[:500]
            if not title and not snippet:
                continue
            line = f"{idx}. {title}"
            if snippet:
                line += f"\n摘要：{snippet}"
            if url:
                line += f"\nURL：{url}"
            lines.append(line)
        context = "\n".join(lines).strip()
        if len(lines) <= 2:
            return ""
        logger.info("[comfyui_agent] prompt web search ok results=%s chars=%s", len(lines) - 2, len(context))
        return context

    async def _generate_prompt_tags_with_llm(
        self,
        *,
        provider_id: str,
        llm_prompt: str,
        use_deep_thinking: bool,
        default_character: bool,
        character_name: str = "",
    ) -> str:
        if character_name:
            character_rule = f"不要输出固定角色“{character_name}”的固有外观设定。"
        else:
            character_rule = (
                "不要输出默认角色的固有外观设定。"
                if default_character
                else "用户已指定其它角色时，可以并且应该输出该角色的固有外观设定。"
            )
        kwargs: dict[str, Any] = {
            "chat_provider_id": provider_id,
            "prompt": llm_prompt,
            "system_prompt": (
                "你是 Anima 模型的 Danbooru tag 提示词助手。"
                "请在内部充分推理和校验参考对象的视觉特征，但不要输出思考过程。"
                "只输出英文 danbooru tags，用英文逗号分隔。"
                "不要解释，不要 Markdown，不要输出质量词或画师词。"
                f"{character_rule}"
            ),
            "max_tokens": self._int("prompt_builder_max_tokens", 700),
        }
        if use_deep_thinking:
            kwargs["reasoning_effort"] = self._str("prompt_builder_reasoning_effort", "max") or "max"
            kwargs["thinking"] = {"type": "enabled"}
        response = await self.context.llm_generate(**kwargs)
        return str(getattr(response, "completion_text", "") or "").strip()

    async def _resolve_danbooru_core_tags(
        self,
        *,
        llm_content: str,
        user_prompt: str,
        default_character: bool,
    ) -> str:
        if not llm_content or not self._bool("danbooru_core_tag_lookup_enabled", True):
            return llm_content
        base_urls_text = self._str("danbooru_tag_base_urls", "").strip()
        if base_urls_text:
            base_urls = tuple(
                item.strip()
                for item in re.split(r"[,;\n]+", base_urls_text)
                if item.strip()
            )
        else:
            base_urls = DEFAULT_DONMAI_BASE_URLS
        timeout = max(1.0, min(self._float("danbooru_tag_lookup_timeout", 6.0), 20.0))
        max_candidates = max(1, min(self._int("danbooru_tag_max_candidates", 6), 16))
        user_agent = self._str("danbooru_tag_user_agent", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT
        try:
            result = await asyncio.to_thread(
                resolve_core_tags,
                llm_content,
                user_prompt=user_prompt,
                allow_insert=not default_character,
                max_candidates=max_candidates,
                timeout=timeout,
                donmai_base_urls=base_urls,
                user_agent=user_agent,
                cache=self._danbooru_tag_cache,
            )
        except Exception as exc:
            logger.warning("[comfyui_agent] danbooru core tag lookup failed: %s", exc)
            return llm_content
        for old, new, count, source in result.replacements:
            logger.info(
                "[comfyui_agent] danbooru core tag resolved: %s -> %s post_count=%s source=%s",
                old,
                new,
                count,
                source,
            )
        for new, count, source in result.inserted:
            logger.info(
                "[comfyui_agent] danbooru core tag inserted: %s post_count=%s source=%s",
                new,
                count,
                source,
            )
        return result.text

    async def _build_anima_prompt(
        self,
        event: AstrMessageEvent,
        user_prompt: str,
        mode: str = "txt2img",
    ) -> str:
        prompt = str(user_prompt or "").strip()
        if not self._bool("prompt_optimize_enabled", True):
            return prompt
        raw_mode, raw_prompt = strip_raw_prefix(prompt)
        if raw_mode:
            logger.info("[comfyui_agent] prompt builder skipped: raw tags mode")
            return raw_prompt

        provider_id = await self._current_chat_provider_id(event)
        if not provider_id:
            logger.warning("[comfyui_agent] prompt builder has no provider; using original prompt")
            return prompt

        use_default_character = wants_default_character(
            prompt,
            self._bool("default_character_enabled", False),
        )
        fixed_character = selected_fixed_character(prompt, dict(self.config))
        fixed_character_name = fixed_character[0] if fixed_character else ""
        if fixed_character:
            use_default_character = True
        use_sensual_mode = wants_sensual_mode(prompt, dict(self.config))
        required_core_tags = (
            required_core_tags_for_prompt(prompt) if not use_default_character else ()
        )
        logger.info(
            "[comfyui_agent] prompt builder input default_character=%s fixed_character=%s sensual=%s required_core_tags=%s prompt=%s",
            use_default_character,
            fixed_character_name or "none",
            use_sensual_mode,
            ",".join(required_core_tags) or "none",
            prompt[:180],
        )
        search_reason = self._keyword_reason(prompt, WEB_SEARCH_KEYWORDS)
        thinking_reason = self._keyword_reason(prompt, DEEP_THINKING_KEYWORDS)
        use_web_search = bool(search_reason) and self._bool("prompt_builder_web_search_enabled", True)
        use_deep_thinking = bool(thinking_reason) and self._bool("prompt_builder_deep_thinking_enabled", True)
        logger.info(
            "[comfyui_agent] prompt strategy web_search=%s deep_thinking=%s search_reason=%s thinking_reason=%s",
            use_web_search,
            use_deep_thinking,
            search_reason or "none",
            thinking_reason or "none",
        )
        search_context = await self._prompt_search_context(event, prompt) if use_web_search else ""
        llm_prompt = build_llm_prompt(
            prompt,
            search_context=search_context,
            default_character=use_default_character,
            character_name=fixed_character_name,
            sensual_mode=use_sensual_mode,
            mode=mode,
        )
        try:
            llm_content = await self._generate_prompt_tags_with_llm(
                provider_id=provider_id,
                llm_prompt=llm_prompt,
                use_deep_thinking=use_deep_thinking,
                default_character=use_default_character,
                character_name=fixed_character_name,
            )
        except Exception as exc:
            if not use_deep_thinking:
                logger.warning("[comfyui_agent] prompt builder LLM failed: %s", exc)
                llm_content = ""
            else:
                logger.warning(
                    "[comfyui_agent] prompt builder deep thinking failed, retrying without it: %s",
                    exc,
                )
                try:
                    llm_content = await self._generate_prompt_tags_with_llm(
                        provider_id=provider_id,
                        llm_prompt=llm_prompt,
                        use_deep_thinking=False,
                        default_character=use_default_character,
                        character_name=fixed_character_name,
                    )
                except Exception as retry_exc:
                    logger.warning("[comfyui_agent] prompt builder LLM failed: %s", retry_exc)
                    llm_content = ""

        llm_content = await self._resolve_danbooru_core_tags(
            llm_content=llm_content,
            user_prompt=prompt,
            default_character=use_default_character,
        )
        built = build_final_prompt(
            user_prompt=prompt,
            llm_content=llm_content,
            config=dict(self.config),
            required_core_tags=required_core_tags,
        )
        logger.info(
            "[comfyui_agent] prompt built raw=%s web_search=%s deep_thinking=%s character=%s sensual=%s default_character=%s default_style=%s required_core_tags=%s content_chars=%s final_chars=%s final_head=%s",
            built.raw_mode,
            bool(search_context),
            use_deep_thinking,
            built.character_name or "none",
            built.used_sensual_mode,
            built.used_default_character,
            built.used_default_style,
            ",".join(built.required_core_tags) or "none",
            len(built.content_tags),
            len(built.final_prompt),
            built.final_prompt[:500],
        )
        return built.final_prompt

    async def _start_comfyui_process(self) -> dict[str, Any]:
        command = self._str("startup_command", "").strip()
        workdir = self._str("startup_workdir", "").strip()
        visible_window = self._bool("startup_visible_window", True)
        if not command:
            return {"ok": False, "error": "startup_command_not_configured"}
        if workdir and not Path(workdir).exists():
            return {"ok": False, "error": f"startup_workdir_not_found: {workdir}"}
        flags = 0
        if sys.platform == "win32" and not visible_window:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        elif sys.platform == "win32":
            flags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("TQDM_DISABLE", "1")
        try:
            if sys.platform == "win32" and visible_window:
                command_path = Path(command.strip('"'))
                if command_path.suffix.lower() in {".bat", ".cmd"} and command_path.exists():
                    cmd_args = [
                        "cmd.exe",
                        "/k",
                        "call",
                        str(command_path),
                    ]
                else:
                    cmd_args = [
                        "cmd.exe",
                        "/s",
                        "/k",
                        f'"title AstrBot ComfyUI && chcp 65001 >nul && {command}"',
                    ]
                await asyncio.create_subprocess_exec(
                    *cmd_args,
                    cwd=workdir or str(ROOT),
                    env=env,
                    creationflags=flags,
                )
            else:
                await asyncio.create_subprocess_shell(
                    command,
                    cwd=workdir or str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    creationflags=flags,
                )
        except Exception as exc:
            return {"ok": False, "error": f"startup_failed: {type(exc).__name__}: {exc}"}
        logger.info(
            "[comfyui_agent] auto_start launched command=%s workdir=%s visible_window=%s",
            command,
            workdir or str(ROOT),
            visible_window,
        )
        return {"ok": True}

    async def _ensure_comfyui_ready(self, event: AstrMessageEvent) -> dict[str, Any]:
        status = await self._run_tool(["status"])
        if self._comfyui_ready(status):
            return {"ok": True, "status": status}
        if not self._bool("auto_start", False):
            return {"ok": False, "error": "comfyui_offline", "status": status}
        if not self._is_auto_start_allowed(event):
            return {"ok": False, "error": "auto_start_not_permitted", "status": status}

        async with self._startup_lock:
            status = await self._run_tool(["status"])
            if self._comfyui_ready(status):
                return {"ok": True, "status": status}

            launched = await self._start_comfyui_process()
            if not launched.get("ok"):
                return launched

            wait_seconds = max(5, self._int("startup_wait_seconds", 120))
            poll_interval = max(1, self._int("startup_poll_interval", 3))
            deadline = asyncio.get_running_loop().time() + wait_seconds
            last_status: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                last_status = await self._run_tool(["status"])
                if self._comfyui_ready(last_status):
                    logger.info("[comfyui_agent] auto_start ready")
                    return {"ok": True, "status": last_status}
            return {
                "ok": False,
                "error": f"auto_start_timeout_after_{wait_seconds}s",
                "status": last_status,
            }

    def _failure_reason(self, payload: dict[str, Any]) -> str:
        detail = str(payload.get("error") or "unknown_error")
        if detail.startswith(("timeout_after_", "local_wait_timeout_after_")):
            return "ComfyUI 排队或生成过久"
        if detail == "http_error":
            return f"ComfyUI 接口请求失败 HTTP {payload.get('status_code')}"
        if detail == "workflow_failed":
            return "ComfyUI 工作流执行失败"
        if detail == "no image found in history":
            return "ComfyUI 完成了任务但没有产出图片"
        if detail == "no recent image found in workspace inputs":
            return "没有找到最近收到的图片"
        if detail == "reference_image_not_found":
            return "没有拿到参考图。请直接带图发送，或引用一条包含图片的消息再使用 /anm"
        if "unsupported_size" in detail:
            return "尺寸不在当前 Anima 预设范围内"
        return detail[:300]

    async def _send_payload(self, event: AstrMessageEvent, payload: dict[str, Any]) -> str:
        if not payload.get("ok"):
            reason = self._failure_reason(payload)
            await event.send(event.plain_result(f"ComfyUI 操作失败：{reason}。"))
            return f"ComfyUI operation failed. Reason: {reason}."

        outputs = [str(item) for item in payload.get("outputs", []) if Path(str(item)).exists()]
        if not outputs:
            await event.send(event.plain_result("ComfyUI 完成了任务，但没有拿到可发送的图片。"))
            return "ComfyUI operation finished with no output image."

        if self._bool("send_result_to_chat", True):
            for output in outputs[: self._int("max_send_images", 1)]:
                try:
                    await event.send(event.image_result(output))
                except Exception as exc:
                    is_action_failed = ActionFailed is not None and isinstance(exc, ActionFailed)
                    retcode = getattr(exc, "retcode", None)
                    wording = str(getattr(exc, "wording", "") or getattr(exc, "message", "") or exc)
                    if is_action_failed and (retcode == 1200 or "Timeout" in wording):
                        logger.warning(
                            "[comfyui_agent] image generated but platform send ACK timed out; "
                            "the image may already be delivered. path=%s error=%s",
                            output,
                            wording[:500],
                        )
                        return "ComfyUI image created; platform send acknowledgement timed out: " + ", ".join(outputs)
                    logger.warning(
                        "[comfyui_agent] image generated but sending failed. path=%s error=%s: %s",
                        output,
                        type(exc).__name__,
                        str(exc)[:500],
                    )
                    return "ComfyUI image created but sending failed: " + ", ".join(outputs)
        return "ComfyUI image created and sent: " + ", ".join(outputs)

    async def _generate_payload(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
    ) -> dict[str, Any]:
        if not self._is_allowed(event):
            return {"ok": False, "error": "not_permitted"}
        ready = await self._ensure_comfyui_ready(event)
        if not ready.get("ok"):
            return ready
        prompt = str(prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "missing_prompt"}
        prompt = await self._augment_prompt_with_reference_image(event, prompt)
        if prompt is None:
            return {"ok": False, "error": "reference_image_not_found"}
        prompt = await self._build_anima_prompt(event, prompt)
        args = ["generate", "--prompt", prompt]
        if width:
            args.extend(["--width", str(int(width))])
        if height:
            args.extend(["--height", str(int(height))])
        if steps:
            args.extend(["--steps", str(int(steps))])
        if cfg:
            args.extend(["--cfg", str(float(cfg))])
        return await self._run_tool(args)

    async def _generate(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
    ) -> str:
        payload = await self._generate_payload(
            event, prompt, width=width, height=height, steps=steps, cfg=cfg
        )
        return await self._send_payload(event, payload)

    async def _edit(self, event: AstrMessageEvent, prompt: str) -> str:
        if not self._bool("img2img_enabled", False):
            return "图生图/改图功能已关闭。现在只保留文生图、去背景、法术解析和反推。"
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        ready = await self._ensure_comfyui_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        prompt = str(prompt or "").strip()
        if not prompt:
            return "Missing ComfyUI edit prompt."
        image_input = await self._event_image_input(event)
        if self._bool("prompt_optimize_img2img_enabled", True):
            prompt = await self._build_anima_prompt(event, prompt, mode="img2img")
        payload = await self._run_tool(["edit", "--prompt", prompt, "--input", image_input or "latest"])
        return await self._send_payload(event, payload)

    async def _spell(self, event: AstrMessageEvent) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        payload = await self._image_spell_payload(event)
        return self._format_spell_payload(payload)

    async def _reverse(self, event: AstrMessageEvent) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        image_input = await self._event_image_input(event)
        tags = await self._reverse_image_tags(event, image_input)
        if not tags:
            return "图片反推失败：没有可用图片或视觉模型调用失败。"
        return "图片反推 tags：\n" + self._shorten(tags, 2200)

    async def _upscale(self, event: AstrMessageEvent) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        ready = await self._ensure_comfyui_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        image_input = await self._event_image_input(event)
        payload = await self._run_tool(["upscale", "--input", image_input or "latest"])
        return await self._send_payload(event, payload)

    async def _remove_bg(self, event: AstrMessageEvent) -> str:
        if not self._is_allowed(event):
            return "ComfyUI agent is disabled or not permitted for this user."
        ready = await self._ensure_comfyui_ready(event)
        if not ready.get("ok"):
            return await self._send_payload(event, ready)
        image_input = await self._event_image_input(event)
        payload = await self._run_tool(["remove-bg", "--input", image_input or "latest"])
        return await self._send_payload(event, payload)

    @filter.command_group("anm", alias={"comfyui", "anima"})
    def comfyui_group(self):
        pass

    @filter.event_message_type(EventMessageType.ALL, priority=sys.maxsize - 2)
    async def hard_route_comfyui(self, event: AstrMessageEvent):
        route = self._parse_hard_route(event.get_message_str())
        if not route:
            route = self._parse_hard_route(event.get_message_outline())
        if not route:
            return
        if not self._is_allowed(event):
            await event.send(event.plain_result("ComfyUI agent is disabled or not permitted for this user."))
            event.stop_event()
            return

        action, prompt = route
        logger.info("[comfyui_agent] hard route action=%s sender=%s", action, event.get_sender_id())
        event.stop_event()

        if action == "help":
            await event.send(event.plain_result(self._help_text()))
            return

        if action == "status":
            payload = await self._run_tool(["status"])
            if payload.get("ok"):
                lines = [
                    "ComfyUI agent 状态：",
                    f"- 启用：{payload.get('enabled')}",
                    f"- 地址：{payload.get('base_url')}",
                    f"- 工作流：{payload.get('workflow')}",
                    f"- 尺寸预设：{', '.join(payload.get('allowed_sizes') or [])}",
                    f"- ComfyUI：{payload.get('comfyui_version')}",
                    f"- GPU：{payload.get('gpu')}",
                    f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
                    f"- UNET 可用：{payload.get('unet_available')}",
                    f"- CLIP 可用：{payload.get('clip_available')}",
                    f"- VAE 可用：{payload.get('vae_available')}",
                ]
                await event.send(event.plain_result("\n".join(lines)))
            else:
                await event.send(event.plain_result(f"ComfyUI 状态检查失败：{payload.get('error')}"))
            return

        if action == "edit" and not self._bool("img2img_enabled", False):
            await event.send(event.plain_result(await self._edit(event, prompt)))
            return

        if action in {"generate", "edit"} and not prompt:
            hint = "请在后面写完整 prompt 或 tags。" if action == "generate" else "请在后面写改图 prompt。"
            await event.send(event.plain_result(hint))
            return

        if action == "generate":
            await self._generate(event, prompt)
        elif action == "edit":
            await self._edit(event, prompt)
        elif action == "disabled_upscale":
            await event.send(event.plain_result("放大功能已关闭。"))
        elif action == "remove_bg":
            await self._remove_bg(event)
        elif action == "spell":
            await event.send(event.plain_result(await self._spell(event)))
        elif action == "reverse":
            await event.send(event.plain_result(await self._reverse(event)))

    @comfyui_group.command("help", alias={"帮助", "指令表", "指令", "菜单"})
    async def cmd_help(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(self._help_text())

    @comfyui_group.command("status", alias={'״̬'})
    async def cmd_status(self, event: AstrMessageEvent):
        event.stop_event()
        if not self._is_allowed(event):
            yield event.plain_result("ComfyUI agent is disabled or not permitted for this user.")
            return
        payload = await self._run_tool(["status"])
        if payload.get("ok"):
            lines = [
                "ComfyUI agent 状态：",
                f"- 启用：{payload.get('enabled')}",
                f"- 地址：{payload.get('base_url')}",
                f"- 工作流：{payload.get('workflow')}",
                f"- 尺寸预设：{', '.join(payload.get('allowed_sizes') or [])}",
                f"- ComfyUI：{payload.get('comfyui_version')}",
                f"- GPU：{payload.get('gpu')}",
                f"- 显存：{payload.get('vram_free_mb')} / {payload.get('vram_total_mb')} MB",
                f"- UNET 可用：{payload.get('unet_available')}",
                f"- CLIP 可用：{payload.get('clip_available')}",
                f"- VAE 可用：{payload.get('vae_available')}",
            ]
            yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result(f"ComfyUI 状态检查失败：{payload.get('error')}")

    @comfyui_group.command("generate", alias={"生图", "画图"})
    async def cmd_generate(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        prompt = str(prompt or "").strip()
        if not prompt:
            yield event.plain_result("请在命令后写完整 prompt 或 tags。")
            return
        message = await self._generate(event, prompt)
        logger.info("[comfyui_agent] command generate result: %s", message)

    @comfyui_group.command("edit", alias={"改图", "图生图", "风格化", "重绘"})
    async def cmd_edit(self, event: AstrMessageEvent, prompt: GreedyStr):
        event.stop_event()
        if not self._bool("img2img_enabled", False):
            yield event.plain_result(await self._edit(event, str(prompt or "").strip()))
            return
        prompt = str(prompt or "").strip()
        if not prompt:
            yield event.plain_result("请在命令后写改图 prompt。")
            return
        message = await self._edit(event, prompt)
        logger.info("[comfyui_agent] command edit result: %s", message)

    @comfyui_group.command("upscale", alias={"放大", "高清", "高清修复"})
    async def cmd_upscale(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result("放大功能已关闭。")

    @comfyui_group.command("remove_bg", alias={"抠图", "去背景", "去除背景"})
    async def cmd_remove_bg(self, event: AstrMessageEvent):
        event.stop_event()
        message = await self._remove_bg(event)
        logger.info("[comfyui_agent] command remove_bg result: %s", message)

    @comfyui_group.command("spell", alias={"解析法术", "法术解析", "读取法术", "提取提示词", "读取提示词"})
    async def cmd_spell(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._spell(event))

    @comfyui_group.command("reverse", alias={"反推", "图片反推", "反推提示词"})
    async def cmd_reverse(self, event: AstrMessageEvent):
        event.stop_event()
        yield event.plain_result(await self._reverse(event))

    @filter.llm_tool(name="comfyui_status")
    async def comfyui_status(self, event: AstrMessageEvent) -> str:
        """Check whether local ComfyUI is online and ready.

        Args:
        """
        payload = await self._run_tool(["status"])
        if not payload.get("ok"):
            return f"ComfyUI status failed: {payload.get('error')}"
        return (
            "ComfyUI status: "
            f"enabled={payload.get('enabled')}, "
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

    @filter.llm_tool(name="comfyui_generate")
    async def comfyui_generate(
        self,
        event: AstrMessageEvent,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
    ) -> str:
        """Generate an image with local ComfyUI from the provided prompt/tags.

        Args:
            prompt(string): Complete prompt or tags to send to ComfyUI unchanged.
            width(number): Optional width from the allowed size list.
            height(number): Optional height paired with width.
            steps(number): Optional sampling steps.
            cfg(number): Optional CFG scale.
        """
        return await self._generate(
            event, prompt, width=width, height=height, steps=steps, cfg=cfg
        )

    @filter.llm_tool(name="comfyui_edit")
    async def comfyui_edit(self, event: AstrMessageEvent, prompt: str) -> str:
        """Edit the most recent chat image with local ComfyUI img2img.

        Args:
            prompt(string): Complete img2img prompt or tags.
        """
        return await self._edit(event, prompt)

    @filter.llm_tool(name="comfyui_remove_bg")
    async def comfyui_remove_bg(self, event: AstrMessageEvent) -> str:
        """Remove the background from the most recent chat image with local ComfyUI.

        Args:
        """
        return await self._remove_bg(event)

    @filter.llm_tool(name="comfyui_extract_prompt")
    async def comfyui_extract_prompt(self, event: AstrMessageEvent) -> str:
        """Extract embedded generation prompt/metadata from the most recent or quoted image.

        Args:
        """
        return await self._spell(event)

    @filter.llm_tool(name="comfyui_reverse_prompt")
    async def comfyui_reverse_prompt(self, event: AstrMessageEvent) -> str:
        """Reverse-engineer danbooru tags from the most recent or quoted image using a vision model.

        Args:
        """
        return await self._reverse(event)
