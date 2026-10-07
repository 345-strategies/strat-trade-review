#!/usr/bin/env python3
"""Turn a strat_review.py output folder into a post to share (Discord by default).

Writes, next to review.json:

  share/post.md     the message text, under Discord's 2,000 character limit, no tables
                    (Discord does not render Markdown tables; the alternatives go in a code block)
  share/card.png    a 1200x675 summary card: result, Strat context, the clean trigger, alternatives in R
  share/chart.png   a copy of the review chart for the main position

Attach card.png and chart.png to the message. Green and red mean bull and bear here, never
good and bad, so the P/L on the card is white whether it is a gain or a loss.

  python3 share_post.py --review review_out --lesson "Wait for the 30m trigger." [--r-only] [--handle @me]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import textwrap
from datetime import date
from pathlib import Path

BULL, BEAR = "#4caf50", "#f23645"   # TheStrat Suite 2u / 2d
FG, MUTED, BG, PANEL = "#e6e6e6", "#9a9a9a", "#0f0f0f", "#1a1a1a"
DISCORD_LIMIT = 2000


def money(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def r_of(x: float, risk: float | None) -> str:
    return f"{x / risk:+.1f}R" if risk else ""


def short_plan(plan: str) -> str:
    """Trim the review's long plan labels to something that fits a code block line."""
    plan = re.sub(r" \((\d{1,2}:\d{2} [AP]?M? ?ET)\)", "", plan)          # keep local time only
    plan = re.sub(r"\(trail stop [^)]*\)", "trailed", plan)
    plan = re.sub(r"Clean Strat: .*?on (\S+ \S+) trigger.*", r"Clean Strat (\1 trigger)", plan)
    return plan if len(plan) <= 44 else plan[:43] + "…"


def card_label(plan: str) -> str:
    """Short names for the card's alternatives panel."""
    if plan.startswith("Clean Strat"):
        m = re.search(r"on (\S+ \S+) trigger", plan)
        return f"Clean Strat, {m.group(1)}" if m else "Clean Strat"
    for pat, name in [(r"^Hold all", "Hold all"), (r"^Your exits on (\d+), (\d+) runners?", r"Your exits, \2 held"),
                      (r"^All .* out at T1", "All out at T1"), (r"^(\d+) at T1, (\d+) runner", r"\1 at T1, \2 trailed")]:
        m = re.match(pat, plan)
        if m:
            return m.expand(name)
    return plan if len(plan) <= 30 else plan[:29] + "…"


def main_position(rep: dict) -> dict:
    return max(rep["positions"], key=lambda p: abs(p["qty"] * (p.get("avg_entry") or 0)))


def first_fill_context(pos: dict) -> tuple[str, str]:
    f = pos["fills"][0]
    cells = [f"{tf} {st['combo']}{'' if st.get('sign') is None else (' +' if st['sign'] else ' -')}"
             for tf, st in f["states"].items()]
    return f["continuity"], " | ".join(cells)


def build_text(rep: dict, pos: dict, args) -> str:
    risk = (pos.get("clean") or {}).get("risk")
    show_money = not args.r_only or not risk
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    arrow = "🟢 BULL" if pos["direction"] == "BULL" else "🔴 BEAR"
    res = []
    if show_money:
        res.append(money(pos["pnl"]))
    if risk:
        res.append(r_of(pos["pnl"], risk))
    cont, _ = first_fill_context(pos)
    lines = [f"**{pos['label']} · {day:%b %-d, %Y}** · {arrow}" + (f" · {args.handle}" if args.handle else ""),
             f"**Result:** {' / '.join(res)} on {pos['qty']:g} {'contracts' if pos['asset'] != 'stock' else 'shares'}"]
    if args.lesson:
        lines.append(f"**Lesson:** {args.lesson}")
    lines.append(f"**At entry:** continuity {cont}" + (f"; flags {', '.join(pos['flags'])}" if pos["flags"] else ""))
    c = pos.get("clean")
    clean_alt = next((a for a in pos["alternatives"] if a["plan"].startswith("Clean Strat")), None)
    if c and clean_alt:
        m = re.search(r"on (\S+ \S+) trigger ([\d.]+) \(([^()]*?)(?: \(|\))", clean_alt["plan"])
        stop = re.search(r"stop ([\d.]+)", clean_alt["plan"])
        if m:
            lines.append(f"**Clean Strat:** {m.group(1)} trigger {m.group(2)} at {m.group(3)}"
                         + (f", stop {stop.group(1)}" if stop else "")
                         + f" → {r_of(c['pnl'], risk)}" + (f" ({money(c['pnl'])})" if show_money else ""))
    dw = rep.get("day_worst")
    if dw and rep.get("max_daily_loss"):
        lines.append(f"**Worst point:** {money(dw['pnl'])} vs {money(-abs(rep['max_daily_loss']))} daily limit"
                     if show_money else
                     f"**Worst point:** {abs(min(dw['pnl'], 0)) / abs(rep['max_daily_loss']):.0%} of the daily loss limit used")
    rows = []
    for a in pos["alternatives"]:
        val = r_of(a["pnl"], risk) if risk else ""
        if show_money:
            val = f"{money(a['pnl']):>10} {val:>6}"
        rows.append(f"{short_plan(a['plan']):<45}{val}")
    tail = []
    if any("estimate" in a["source"].lower() or "black" in a["source"].lower() for a in pos["alternatives"]):
        tail.append("_Option alternatives are Black-Scholes estimates, not real marks._")
    if args.notes:
        tail.append(args.notes)
    tail.append("_TheStrat review, 5m/15m/30m/60m. Not advice._")
    text = "\n".join(lines + ["```", *rows, "```"] + tail)
    while len(text) > DISCORD_LIMIT and len(rows) > 2:   # keep Actual and Clean Strat, drop the middle
        rows.pop(-2)
        text = "\n".join(lines + ["```", *rows, "```"] + tail)
    return text


def card(path: Path, rep: dict, pos: dict, args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    risk = (pos.get("clean") or {}).get("risk")
    show_money = not args.r_only or not risk
    fig = plt.figure(figsize=(12, 6.75), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 675)
    t = lambda x, y, s, **k: ax.text(x, y, s, color=k.pop("color", FG), fontsize=k.pop("size", 14),
                                     va=k.pop("va", "top"), ha=k.pop("ha", "left"), **k)
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    t(40, 640, pos["label"], size=30, weight="bold")
    t(40, 592, f"{day:%A %b %-d, %Y}" + (f"   {args.handle}" if args.handle else ""), color=MUTED, size=15)
    bull = pos["direction"] == "BULL"
    ax.add_patch(plt.Rectangle((1040, 600), 120, 40, color=BULL if bull else BEAR))
    t(1100, 620, "BULL" if bull else "BEAR", ha="center", va="center", size=16, weight="bold", color="#0f0f0f")

    big = r_of(pos["pnl"], risk) if (args.r_only and risk) else money(pos["pnl"])
    t(40, 540, "RESULT", color=MUTED, size=12)
    t(40, 515, big, size=46, weight="bold")
    sub = []
    if risk and not args.r_only:
        sub.append(r_of(pos["pnl"], risk))
    sub.append(f"{pos['qty']:g} {'contracts' if pos['asset'] != 'stock' else 'shares'}")
    t(40, 450, "   ".join(sub), color=MUTED, size=15)

    cont, cells = first_fill_context(pos)
    t(40, 395, "AT ENTRY", color=MUTED, size=12)
    t(40, 372, f"Continuity: {cont}", size=16)
    states = pos["fills"][0]["states"]
    for i, (tf, st) in enumerate(states.items()):          # one column per timeframe
        x = 40 + i * 112
        sign = st.get("sign")
        t(x, 340, tf, size=11, color=MUTED)
        t(x, 320, st["combo"].replace("(new)", "new"), size=12, family="monospace",
          color=FG if sign is None else (BULL if sign else BEAR))
    y = 288
    for line in textwrap.wrap("  ".join(pos["flags"]), 60)[:2]:
        t(40, y, line, size=11, color=MUTED, family="monospace")
        y -= 20
    if args.lesson:
        y -= 18
        t(40, y, "LESSON", color=MUTED, size=12)
        y -= 24
        for line in textwrap.wrap(args.lesson, 46)[:3]:
            t(40, y, line, size=17, style="italic")
            y -= 28

    ax.add_patch(plt.Rectangle((640, 40), 520, 380, color=PANEL))
    t(660, 405, "ALTERNATIVES" + (" (R)" if risk else ""), color=MUTED, size=12)
    y = 375
    for a in pos["alternatives"][:7]:
        t(660, y, card_label(a["plan"]), size=12)
        val = r_of(a["pnl"], risk) if risk else money(a["pnl"])
        if show_money and risk:
            val = f"{money(a['pnl'])}  {val}"
        t(1140, y, val, size=12, ha="right", family="monospace")
        y -= 44
    t(40, 40, "TheStrat review · 5m / 15m / 30m / 60m · not advice", color=MUTED, size=11, va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True, help="Folder strat_review.py wrote (has review.json)")
    ap.add_argument("--lesson", help="One sentence: the lesson, in the trader's words if possible")
    ap.add_argument("--notes", help="Optional extra line, e.g. what you would do next time")
    ap.add_argument("--handle", help="Optional name or @handle to show")
    ap.add_argument("--r-only", action="store_true", help="Show results in R only, no dollar amounts")
    ap.add_argument("--position", type=int, help="Which position to share (1-based); default the largest")
    args = ap.parse_args(argv)

    folder = Path(args.review)
    rep = json.loads((folder / "review.json").read_text())
    if not rep.get("positions"):
        raise SystemExit("review.json has no positions")
    pos = rep["positions"][args.position - 1] if args.position else main_position(rep)
    out = folder / "share"
    out.mkdir(exist_ok=True)
    text = build_text(rep, pos, args)
    (out / "post.md").write_text(text + "\n")
    made = ["post.md"]
    try:
        card(out / "card.png", rep, pos, args)
        made.append("card.png")
    except ImportError:
        print("matplotlib not installed: skipped card.png")
    if pos.get("chart") and (folder / pos["chart"]).exists():
        shutil.copy(folder / pos["chart"], out / "chart.png")
        made.append("chart.png")
    print(text)
    print(f"\n{len(text)} characters (Discord limit {DISCORD_LIMIT}). Wrote {', '.join(made)} in {out}")


if __name__ == "__main__":
    main()
