import sys
import os
from pathlib import Path

# Add project root, api directory, /var/task, and current working dir to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for candidate_path in [str(root_dir), str(current_dir), "/var/task", "/var/task/api", os.getcwd()]:
    if candidate_path and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

try:
    from app.main import app
except ImportError:
    try:
        from api.app.main import app
    except ImportError as e:
        import traceback
        traceback.print_exc()
        raise e
