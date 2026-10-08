"""Build one upload zip per skill in skills/ (dist/<skill>.zip), the files people upload (Claude.ai, ChatGPT).

Skips Python bytecode and other local clutter, so running the scripts before a rebuild
does not leak __pycache__ into the upload.
"""
import zipfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".pytest_cache", "strat_review_out", "share"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store"}

root = Path(__file__).resolve().parents[1]
(root / "dist").mkdir(exist_ok=True)

for src in sorted(p for p in (root / "skills").iterdir() if (p / "SKILL.md").exists()):
    if "disable-model-invocation: true" in (src / "SKILL.md").read_text():
        continue  # slash-command-only skills (e.g. strat-review) are for Claude Code; no upload zip
    out = root / "dist" / f"{src.name}.zip"
    files = sorted(
        p for p in src.rglob("*")
        if p.is_file()
        and not SKIP_DIRS.intersection(p.relative_to(src).parts)
        and p.suffix not in SKIP_SUFFIXES
        and p.name not in SKIP_NAMES
    )
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, Path(src.name) / p.relative_to(src))
    print(f"wrote {out} ({len(files)} files)")
