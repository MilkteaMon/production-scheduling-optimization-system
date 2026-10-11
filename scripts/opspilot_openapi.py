import json
from pathlib import Path

from opspilot.api.main import create_app

Path("backend/openapi.json").write_text(
    json.dumps(create_app().openapi(), indent=2), encoding="utf-8"
)
