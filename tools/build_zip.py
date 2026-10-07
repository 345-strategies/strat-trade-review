"""Build dist/strat-trade-review.zip, the file people upload as a skill (Claude.ai, ChatGPT).

Skips Python bytecode and other local clutter, so running the scripts before a rebuild
does not leak __pycache__ into the upload.
"""
import zipfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".pytest_cache", "strat_review_out"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store"}

root = Path(__file__).resolve().parents[1]
src = root / "skills" / "strat-trade-review"
out = root / "dist" / "strat-trade-review.zip"
out.parent.mkdir(exist_ok=True)

files = sorted(
    p for p in src.rglob("*")
    if p.is_file()
    and not SKIP_DIRS.intersection(p.relative_to(src).parts)
    and p.suffix not in SKIP_SUFFIXES
    and p.name not in SKIP_NAMES
)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, Path("strat-trade-review") / p.relative_to(src))
print(f"wrote {out} ({len(files)} files)")
