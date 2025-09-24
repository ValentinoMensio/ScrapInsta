import json
from pathlib import Path

def load_accounts(filepath="src/config/accounts.json"):
    with open(Path(filepath), "r", encoding="utf-8") as f:
        return json.load(f)