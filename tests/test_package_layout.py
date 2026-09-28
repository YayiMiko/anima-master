from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_plugin_root_keeps_only_astrbot_python_entry():
    assert {path.name for path in PLUGIN_DIR.glob("*.py")} == {"main.py"}
    assert (PLUGIN_DIR / "_conf_schema.json").is_file()
    assert (PLUGIN_DIR / "metadata.yaml").is_file()
    assert (PLUGIN_DIR / "agent_tools" / "comfyui_agent.py").is_file()
    for group in ("commands", "prompts", "images", "runtime"):
        assert (PLUGIN_DIR / "anima" / group / "__init__.py").is_file()
