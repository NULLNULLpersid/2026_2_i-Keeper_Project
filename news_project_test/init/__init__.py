"""config.py에서 프로젝트 설정을 가져옵니다."""
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.py"

def reload_config():
    """Load config.py while keeping the existing config module identity."""
    loader = SourceFileLoader("config", str(CONFIG_PATH))
    spec = spec_from_loader("config", loader)
    fresh_module = module_from_spec(spec)
    exec(compile(CONFIG_PATH.read_text(encoding="utf-8"), str(CONFIG_PATH), "exec"), fresh_module.__dict__)
    current_module = sys.modules.get("config")
    if current_module is None:
        sys.modules["config"] = fresh_module
        return fresh_module

    current_module.__dict__.clear()
    current_module.__dict__.update(fresh_module.__dict__)
    sys.modules["config"] = current_module
    return current_module

config = reload_config()