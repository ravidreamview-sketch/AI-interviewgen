"""
Services Package with Backward Compatibility for Legacy app.services module.
"""

import importlib.util
import os
import sys

# Load legacy app/services.py to avoid breaking existing imports:
# from app.services import generate_ai_questions, parse_raw_questions
_legacy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services.py")
if os.path.exists(_legacy_path):
    spec = importlib.util.spec_from_file_location("app._legacy_services", _legacy_path)
    if spec and spec.loader:
        _mod = importlib.util.module_from_spec(spec)
        sys.modules["app._legacy_services"] = _mod
        spec.loader.exec_module(_mod)
        for attr in dir(_mod):
            if not attr.startswith("__"):
                globals()[attr] = getattr(_mod, attr)
