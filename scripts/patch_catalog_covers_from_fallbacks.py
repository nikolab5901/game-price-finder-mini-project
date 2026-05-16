#!/usr/bin/env python3
"""Apply scripts/cover_fallbacks_override.json to game_price_finder/popular_catalog.json in place."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "game_price_finder" / "popular_catalog.json"
GEN_SCRIPT = ROOT / "scripts" / "generate_popular_catalog.py"


def _load_generate_module():
    spec = importlib.util.spec_from_file_location("generate_popular_catalog", GEN_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {GEN_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    gpc = _load_generate_module()
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    gpc.apply_cover_fallback_overrides(entries, gpc.COVER_FALLBACK_PATH)
    missing = sum(1 for e in entries if not (e.get("game") or {}).get("cover_image_url"))
    if missing:
        print(f"ERROR: still {missing} titles without cover_image_url", file=sys.stderr)
        sys.exit(2)
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Patched {CATALOG.relative_to(ROOT)!s}: all covers present.")


if __name__ == "__main__":
    main()
