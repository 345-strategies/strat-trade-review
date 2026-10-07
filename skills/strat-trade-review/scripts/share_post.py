#!/usr/bin/env python3
"""Turn a strat_review.py output folder into a post to share (Discord by default).

Writes, next to review.json:

  share/post.md     the message text, under Discord's 2,000 character limit, no tables
                    (Discord does not render Markdown tables; the alternatives go in a code block)
  share/card.png        a 1200x675 summary card: % return and R, what was with and against the Strat,
                        the state on each timeframe at entry, the alternatives
  share/timeframes.png  the 5m/15m/30m/60m chart with every fill numbered (the main image)
  share/chart.png       the single-timeframe session chart

Attach timeframes.png and card.png to the message. Green and red mean bull and bear here, never
good and bad, so results are white whether they are gains or losses.

With and against the Strat points are drafted from the review (continuity, failed breaks, adds, the
exit against the clean trigger, the loss limit). Pass your own with --pro / --con (repeatable) to replace them.

  python3 share_post.py --review review_out --lesson "Wait for the 30m trigger." [--no-dollars] [--handle @me]
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


def pct_of(x: float, cost: float | None) -> str:
    return f"{x / cost:+.0%}" if cost else ""


def result_parts(pos: dict, show_money: bool) -> tuple[str, list[str]]:
    """Headline number and the smaller ones: % on what was paid first, then R, then dollars."""
    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    parts = [p for p in (pct_of(pos["pnl"], cost), r_of(pos["pnl"], risk)) if p]
    if show_money or not parts:
        parts.append(money(pos["pnl"]))
    return parts[0], parts[1:]


def cc_token(combo: str) -> str:
    return combo.rsplit("-", 1)[-1] if combo else ""


def strat_points(rep: dict, pos: dict) -> tuple[list[str], list[str]]:
    """Draft 'with the Strat' and 'against the Strat' points from the review data."""
    pros, cons = [], []
    bull = pos["direction"] == "BULL"
    tfs = pos.get("tfs") or [tf for tf in pos["fills"][0]["states"] if tf != "D"]
    side0 = pos["fills"][0]["side"]
    entries = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] == side0]
    exits = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] != side0]
    broke, failed = ("2u", "F2u") if bull else ("2d", "F2d")
    against_groups: dict = {}
    for n, f in entries:
        st = f["states"]
        signs = {tf: st[tf].get("sign") for tf in tfs if tf in st}
        against = tuple(tf for tf, sg in signs.items() if sg is not None and sg != bull)
        known = [tf for tf, sg in signs.items() if sg is not None]
        if known and not against and len(known) == len(tfs):
            pros.append(f"#{n} entered with full continuity ({', '.join(tfs)})")
        elif len(against) >= 2:
            against_groups.setdefault(against, []).append(n)
        brk = [tf for tf in tfs if cc_token(st.get(tf, {}).get("combo", "")) == broke]
        fail = [tf for tf in tfs if cc_token(st.get(tf, {}).get("combo", "")) == failed]
        if fail:
            cons.append(f"#{n} took a {fail[0]} break that was failing ({failed})")
        elif brk:
            pros.append(f"#{n} entered on a {brk[0]} {broke} break")
    for against, ns in against_groups.items():
        who = ", ".join(f"#{n}" for n in ns)
        cons.append(f"{who} entered with {', '.join(against)} {'below' if bull else 'above'} their opens")
    if "AVERAGED_DOWN" in pos["flags"]:
        worse = [n for n, f in entries[1:] if (f["price"] < entries[0][1]["price"]) == (side0 == "BUY")]
        cons.append(f"Averaged down at #{', #'.join(map(str, worse))} with no new trigger" if worse
                    else "Averaged down with no new trigger")
    if "EARLY_SESSION" in pos["flags"]:
        cons.append("Entered before 10:00 ET, the noisiest part of the session")
    c = pos.get("clean")
    if c and c.get("time"):
        from datetime import datetime, timedelta
        t0 = datetime.fromisoformat(c["time"])
        mins = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(c.get("tf"), 30)
        early = [n for n, f in exits if t0 - timedelta(minutes=mins) <= datetime.fromisoformat(f["time"]) <= t0 + timedelta(minutes=mins)]
        if early:
            cons.append(f"Sold on the {c['tf']} {c['event']} trigger, which was the real entry")
        risk = c.get("risk")
        if risk and c.get("pnl") is not None:
            if pos["pnl"] >= c["pnl"]:
                pros.append(f"Beat the clean {c['tf']} trigger plan ({r_of(c['pnl'], risk)})")
    dw, lim = rep.get("day_worst"), rep.get("max_daily_loss")
    if dw and lim:
        used = abs(min(dw["pnl"], 0)) / abs(lim)
        if used >= 0.8:
            cons.append(f"Worst point used {used:.0%} of the daily loss limit")
        elif used <= 0.5:
            pros.append(f"Stayed well inside the daily loss limit ({used:.0%} used)")
    if not any(p.startswith("#") for p in cons) and entries and not pros:
        pros.append("No entries against continuity")
    return pros[:3], cons[:5]


def main_position(rep: dict) -> dict:
    return max(rep["positions"], key=lambda p: abs(p["qty"] * (p.get("avg_entry") or 0)))


def first_fill_context(pos: dict) -> tuple[str, str]:
    f = pos["fills"][0]
    cells = [f"{tf} {st['combo']}{'' if st.get('sign') is None else (' +' if st['sign'] else ' -')}"
             for tf, st in f["states"].items()]
    return f["continuity"], " | ".join(cells)


def build_text(rep: dict, pos: dict, args, pros: list[str], cons: list[str]) -> str:
    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    show_money = not args.no_dollars
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    arrow = "🟢 BULL" if pos["direction"] == "BULL" else "🔴 BEAR"
    head, rest = result_parts(pos, show_money)
    unit = "contracts" if pos["asset"] != "stock" else "shares"
    lines = [f"**{pos['label']} · {day:%b %-d, %Y}** · {arrow}" + (f" · {args.handle}" if args.handle else ""),
             f"**Result: {head}**" + (f" ({', '.join(rest)})" if rest else "") + f" on {pos['qty']:g} {unit}"]
    if pros:
        lines.append("**With the Strat**")
        lines += [f"+ {p}" for p in pros]
    if cons:
        lines.append("**Against the Strat**")
        lines += [f"− {p}" for p in cons]
    c = pos.get("clean")
    if c and c.get("trigger"):
        lines.append(f"**Clean Strat:** {c['tf']} {c['event']} trigger {c['trigger']:.2f}, C1 stop {c['stop_c1']:.2f}"
                     f" → {pct_of(c['pnl'], cost) or r_of(c['pnl'], risk)}"
                     + (f", {r_of(c['pnl'], risk)}" if cost and risk else ""))
    if args.lesson:
        lines.append(f"**Lesson:** {args.lesson}")
    rows = []
    for a in pos["alternatives"]:
        cells = [x for x in (pct_of(a["pnl"], cost), r_of(a["pnl"], risk)) if x]
        if show_money:
            cells.append(money(a["pnl"]))
        rows.append(f"{short_plan(a['plan']):<40}" + "".join(f"{x:>11}" for x in cells))
    tail = []
    if any("estimate" in a["source"].lower() or "black" in a["source"].lower() for a in pos["alternatives"]):
        tail.append("_Option alternatives are Black-Scholes estimates, not real marks._")
    if args.notes:
        tail.append(args.notes)
    tail.append("_TheStrat review on 5m/15m/30m/60m. Not advice._")
    text = "\n".join(lines + ["```", *rows, "```"] + tail)
    while len(text) > DISCORD_LIMIT and len(rows) > 2:   # keep Actual and Clean Strat, drop the middle
        rows.pop(-2)
        text = "\n".join(lines + ["```", *rows, "```"] + tail)
    return text


def card(path: Path, rep: dict, pos: dict, args, pros: list[str], cons: list[str]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["text.parse_math"] = False

    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    show_money = not args.no_dollars
    fig = plt.figure(figsize=(12, 6.75), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 675)
    t = lambda x, y, s, **k: ax.text(x, y, s, color=k.pop("color", FG), fontsize=k.pop("size", 14),
                                     va=k.pop("va", "top"), ha=k.pop("ha", "left"), **k)
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    t(40, 640, pos["label"], size=28, weight="bold")
    t(40, 596, f"{day:%A %b %-d, %Y}" + (f"   {args.handle}" if args.handle else ""), color=MUTED, size=14)
    bull = pos["direction"] == "BULL"
    ax.add_patch(plt.Rectangle((1040, 604), 120, 38, color=BULL if bull else BEAR))
    t(1100, 623, "BULL" if bull else "BEAR", ha="center", va="center", size=15, weight="bold", color="#0f0f0f")

    head, rest = result_parts(pos, show_money)
    t(40, 560, head, size=50, weight="bold")
    unit = "contracts" if pos["asset"] != "stock" else "shares"
    t(40, 478, "   ".join(rest + [f"{pos['qty']:g} {unit}"]), color=MUTED, size=15)

    def bullets(y, title, items, mark):
        t(40, y, title, color=MUTED, size=12, weight="bold")
        y -= 24
        for it in items:
            lines = textwrap.wrap(it, 54)[:2]
            t(40, y, mark, size=15, weight="bold")
            for ln in lines:
                t(64, y, ln, size=13.5)
                y -= 22
            y -= 6
        return y - 8

    y = 432
    if pros:
        y = bullets(y, "WITH THE STRAT", pros, "+")
    if cons:
        y = bullets(y, "AGAINST THE STRAT", cons, "−")
    if args.lesson and y > 90:
        t(40, y, "LESSON", color=MUTED, size=12, weight="bold")
        y -= 24
        for ln in textwrap.wrap(args.lesson, 58)[:2]:
            t(40, y, ln, size=14, style="italic")
            y -= 22

    # right panel: state at entry, then the alternatives
    ax.add_patch(plt.Rectangle((650, 40), 510, 540, color=PANEL))
    f0 = pos["fills"][0]
    t(670, 565, f"AT ENTRY #1   ·   {f0['continuity']}", color=MUTED, size=12, weight="bold")
    for i, (tf, st) in enumerate(f0["states"].items()):
        x = 670 + i * 98
        sign = st.get("sign")
        t(x, 535, tf + (" (ctx)" if tf == "D" else ""), size=11, color=MUTED)
        t(x, 512, st["combo"].replace("-(new)", "-new"), size=12, family="monospace",
          color=FG if sign is None else (BULL if sign else BEAR))
    t(670, 470, "ALTERNATIVES", color=MUTED, size=12, weight="bold")
    hdr = [h for h, ok in (("% return", bool(cost)), ("R", bool(risk)), ("$", show_money)) if ok]
    for k, h in enumerate(reversed(hdr)):
        t(1140 - 90 * k, 470, h, color=MUTED, size=11, ha="right")
    y = 440
    for a in pos["alternatives"][:8]:
        t(670, y, card_label(a["plan"]), size=12.5)
        vals = [v for v, ok in ((pct_of(a["pnl"], cost), bool(cost)), (r_of(a["pnl"], risk), bool(risk)),
                                (money(a["pnl"]), show_money)) if ok]
        for k, v in enumerate(reversed(vals)):
            t(1140 - 90 * k, y, v, size=12, ha="right", family="monospace",
              weight="bold" if a["plan"] == "Actual" else "normal")
        y -= 46
    t(40, 30, "TheStrat review · 5m / 15m / 30m / 60m · not advice", color=MUTED, size=11, va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True, help="Folder strat_review.py wrote (has review.json)")
    ap.add_argument("--lesson", help="One sentence: the lesson, in the trader's words if possible")
    ap.add_argument("--notes", help="Optional extra line, e.g. what you would do next time")
    ap.add_argument("--handle", help="Optional name or @handle to show")
    ap.add_argument("--no-dollars", "--r-only", dest="no_dollars", action="store_true",
                    help="Show % and R only, no dollar amounts")
    ap.add_argument("--pro", action="append", help="A 'with the Strat' point (repeatable; replaces the drafted ones)")
    ap.add_argument("--con", action="append", help="An 'against the Strat' point (repeatable; replaces the drafted ones)")
    ap.add_argument("--position", type=int, help="Which position to share (1-based); default the largest")
    args = ap.parse_args(argv)

    folder = Path(args.review)
    rep = json.loads((folder / "review.json").read_text())
    if not rep.get("positions"):
        raise SystemExit("review.json has no positions")
    pos = rep["positions"][args.position - 1] if args.position else main_position(rep)
    out = folder / "share"
    out.mkdir(exist_ok=True)
    auto_pros, auto_cons = strat_points(rep, pos)
    pros = args.pro if (args.pro or args.con) else auto_pros
    cons = args.con if (args.pro or args.con) else auto_cons
    pros, cons = pros or [], cons or []
    text = build_text(rep, pos, args, pros, cons)
    (out / "post.md").write_text(text + "\n")
    made = ["post.md"]
    if pos.get("timeframes_chart") and (folder / pos["timeframes_chart"]).exists():
        shutil.copy(folder / pos["timeframes_chart"], out / "timeframes.png")
        made.append("timeframes.png")
    try:
        card(out / "card.png", rep, pos, args, pros, cons)
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
