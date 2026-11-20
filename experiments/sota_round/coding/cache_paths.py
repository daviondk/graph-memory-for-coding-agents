"""Choose where to keep downloaded fixtures and model weights."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
location = ROOT / "cache-location.txt"
CACHE = Path(os.environ.get("SWE_EXPLORE_CACHE") or (location.read_text().strip() if location.exists() else ROOT)).resolve()
