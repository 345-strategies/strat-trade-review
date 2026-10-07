"""Build dist/strat-trade-review.zip, the file people upload as a skill (Claude.ai, ChatGPT)."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "dist" / "strat-trade-review"
out.parent.mkdir(exist_ok=True)
shutil.make_archive(str(out), "zip", root / "skills", "strat-trade-review")
print(f"wrote {out}.zip")
