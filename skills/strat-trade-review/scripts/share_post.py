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
from datetime import date, datetime, timedelta
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


GOOD, BAD = "#5b9cff", "#f5a524"   # status colors for good / bad calls: never green and red, which mean bull and bear


def strat_checks(rep: dict, pos: dict) -> list[dict]:
    """The same six Strat checks for every trade, each graded good or bad with the evidence.
    A check that the data can't decide (no loss limit given) is left out."""
    bull = pos["direction"] == "BULL"
    tfs = pos.get("tfs") or [tf for tf in pos["fills"][0]["states"] if tf != "D"]
    side0 = pos["fills"][0]["side"]
    entries = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] == side0]
    exits = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] != side0]
    broke, failed = ("2u", "F2u") if bull else ("2d", "F2d")
    away = "below" if bull else "above"
    checks = []

    # 1. on a trigger, and the trigger was holding
    fails, hits = [], []
    for n, f in entries:
        st = f["states"]
        fl = [tf for tf in tfs if cc_token(st.get(tf, {}).get("combo", "")) == failed]
        br = [tf for tf in tfs if cc_token(st.get(tf, {}).get("combo", "")) == broke]
        if fl:
            fails.append(f"#{n} {fl[0]} break already failing ({failed})")
        elif br:
            hits.append(f"#{n} on a {br[0]} {broke} break")
        else:
            fails.append(f"#{n} no {broke} break on any timeframe")
    checks.append(dict(ok=not fails, name="Entered on a live trigger", detail="; ".join(fails or hits)))

    # 2. continuity
    groups: dict = {}
    for n, f in entries:
        against = tuple(tf for tf in tfs if f["states"].get(tf, {}).get("sign") is not None
                        and f["states"][tf]["sign"] != bull)
        if len(against) >= 2:
            groups.setdefault(against, []).append(f"#{n}")
    checks.append(dict(ok=not groups, name="With timeframe continuity",
                       detail="; ".join(f"{', '.join(ns)} with {', '.join(a)} {away} their opens"
                                        for a, ns in groups.items())
                       or f"{', '.join(tfs)} agreed at entry"))

    # 3. adds
    worse = [n for n, f in entries[1:] if (f["price"] < entries[0][1]["price"]) == (side0 == "BUY")]
    checks.append(dict(ok=not worse, name="No averaging down",
                       detail=(f"#{', #'.join(map(str, worse))} added at a worse price with no new trigger"
                               if worse else ("adds only on strength" if len(entries) > 1 else "one entry"))))

    # 4. the exit against the plan: sold on the real trigger, or before the first target
    c = pos.get("clean") or {}
    t1 = pos.get("t1")
    exit_detail, exit_ok = "", True
    if c.get("time") and exits:
        t0 = datetime.fromisoformat(c["time"])
        mins = timedelta(minutes={"5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(c.get("tf"), 30))
        on_trigger = [f"#{n}" for n, f in exits if t0 - mins <= datetime.fromisoformat(f["time"]) <= t0 + mins]
        if on_trigger:
            exit_ok = False
            exit_detail = f"{', '.join(on_trigger)} sold on the {c['tf']} {c['event']} trigger, the real entry"
    if exit_ok and t1 is not None and exits:
        reached = [n for n, f in exits if f.get("underlying") is not None
                   and ((f["underlying"] >= t1) if bull else (f["underlying"] <= t1))]
        # a higher-timeframe signal still in force with the trade at the exit: a 2 (or a failed 2 the other
        # way) in the trade's direction, forming bar on the trade's side of its open
        htf = [tf for tf in ("30m", "60m", "D") if tf in pos["fills"][0]["states"]]
        in_force = []
        for n, f in exits:
            for tf in htf:
                st = f["states"].get(tf, {})
                if st.get("sign") == bull and cc_token(st.get("combo", "")) in ((broke, "F2d") if bull else (broke, "F2u")):
                    in_force.append((n, tf, cc_token(st["combo"])))
                    break
        if in_force and not reached:
            n, tf, tok = in_force[0]
            exit_ok, exit_detail = False, f"#{n} sold with the {tf} {tok} still in force"
        else:
            exit_ok = bool(reached) or pos["pnl"] < 0
            exit_detail = (f"#{reached[0]} out at or past T1 {t1:.2f}" if reached
                           else ("closed for a loss" if pos["pnl"] < 0 else f"out before T1 {t1:.2f}"))
    if exits:
        checks.append(dict(ok=exit_ok, name="Exit by plan", detail=exit_detail))

    # 5. the open
    checks.append(dict(ok="EARLY_SESSION" not in pos["flags"], name="Let the open settle",
                       detail="entered before 10:00 ET" if "EARLY_SESSION" in pos["flags"] else "first entry after 10:00 ET"))

    # 6. the daily loss limit
    dw, lim = rep.get("day_worst"), rep.get("max_daily_loss")
    if dw and lim:
        used = abs(min(dw["pnl"], 0)) / abs(lim)
        checks.append(dict(ok=used < 0.8, name="Inside the loss limit", detail=f"worst point used {used:.0%} of it"))
    return checks


def custom_checks(goods: list[str] | None, bads: list[str] | None) -> list[dict]:
    return ([dict(ok=True, name=g, detail="") for g in goods or []]
            + [dict(ok=False, name=b, detail="") for b in bads or []])


def main_position(rep: dict) -> dict:
    return max(rep["positions"], key=lambda p: abs(p["qty"] * (p.get("avg_entry") or 0)))


def first_fill_context(pos: dict) -> tuple[str, str]:
    f = pos["fills"][0]
    cells = [f"{tf} {st['combo']}{'' if st.get('sign') is None else (' +' if st['sign'] else ' -')}"
             for tf, st in f["states"].items()]
    return f["continuity"], " | ".join(cells)


def build_text(rep: dict, pos: dict, args, checks: list[dict]) -> str:
    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    show_money = not args.no_dollars
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    arrow = "🟢 BULL" if pos["direction"] == "BULL" else "🔴 BEAR"
    head, rest = result_parts(pos, show_money)
    unit = "contracts" if pos["asset"] != "stock" else "shares"
    good = sum(1 for c in checks if c["ok"])
    lines = [f"**{pos['label']} · {day:%b %-d, %Y}** · {arrow}" + (f" · {args.handle}" if args.handle else "")]
    if args.setup:
        lines.append(f"**Setup:** {args.setup}")
    lines += [f"**Result: {head}**" + (f" ({', '.join(rest)})" if rest else "") + f" on {pos['qty']:g} {unit}"]
    if args.lesson:
        lines.append(f"> **Lesson:** {args.lesson}")
    lines.append(f"**Strat checklist: {good} of {len(checks)} good**")
    lines += [f"{'✓ Good' if c['ok'] else '✗ Bad'} · {c['name']}" + (f": {c['detail']}" if c["detail"] else "")
              for c in checks]
    c = pos.get("clean")
    if c and c.get("trigger"):
        lines.append(f"**Clean Strat:** {c['tf']} {c['event']} trigger {c['trigger']:.2f}, C1 stop {c['stop_c1']:.2f}"
                     f" → {pct_of(c['pnl'], cost) or r_of(c['pnl'], risk)}"
                     + (f", {r_of(c['pnl'], risk)}" if cost and risk else ""))
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


def card(path: Path, rep: dict, pos: dict, args, checks: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch
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
    box = lambda x, y, w, h, c, r=8: ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                                                 fc=c, ec="none"))

    # header
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    t(40, 642, pos["label"], size=26, weight="bold")
    t(40, 602, f"{day:%A %b %-d, %Y}" + (f"   ·   {args.setup}" if args.setup else "")
      + (f"   {args.handle}" if args.handle else ""), color=MUTED, size=13)
    bull = pos["direction"] == "BULL"
    box(1060, 610, 100, 34, BULL if bull else BEAR, 6)
    t(1110, 627, ("▲ BULL" if bull else "▼ BEAR"), ha="center", va="center", size=13, weight="bold", color=BG)

    # hero result: one number, then the supporting ones
    head, rest = result_parts(pos, show_money)
    unit = "contracts" if pos["asset"] != "stock" else "shares"
    t(40, 576, head, size=48, weight="bold")
    t(40, 498, "  ·  ".join(rest + [f"{pos['qty']:g} {unit}"]), color=MUTED, size=13)

    # the checklist: same six checks every trade, graded good / bad with icon + label
    good = sum(1 for c in checks if c["ok"])
    t(40, 466, "STRAT CHECKLIST", color=MUTED, size=11, weight="bold")
    t(600, 466, f"{good} of {len(checks)} good", color=FG, size=11, weight="bold", ha="right")
    y = 436
    for c in checks[:6]:
        col = GOOD if c["ok"] else BAD
        ax.add_patch(Circle((52, y - 9), 10, fc=col, ec="none"))
        t(52, y - 9, "✓" if c["ok"] else "✗", ha="center", va="center", size=11, weight="bold", color=BG)
        t(72, y, c["name"], size=12.5, weight="bold")
        t(600, y, "GOOD" if c["ok"] else "BAD", size=9.5, weight="bold", color=col, ha="right")
        if c["detail"]:
            d = c["detail"] if len(c["detail"]) <= 70 else c["detail"][:69] + "…"
            t(72, y - 19, d, size=10.5, color=MUTED)
        y -= 44 if c["detail"] else 30

    # right panel: state at entry, then the alternatives
    box(650, 150, 510, 432, PANEL)
    f0 = pos["fills"][0]
    t(672, 562, "AT ENTRY #1", color=MUTED, size=11, weight="bold")
    t(1138, 562, f0["continuity"], color=FG, size=11, weight="bold", ha="right")
    for i, (tf, st) in enumerate(f0["states"].items()):
        x = 672 + i * 96
        sign = st.get("sign")
        t(x, 534, tf + (" ctx" if tf == "D" else ""), size=10, color=MUTED)
        t(x, 514, st["combo"].replace("-(new)", "-new") + ("" if sign is None else (" ↑" if sign else " ↓")),
          size=11, family="monospace", color=FG if sign is None else (BULL if sign else BEAR))
    ax.plot([672, 1138], [482, 482], color="#2a2a2a", linewidth=1)
    t(672, 468, "IF YOU HAD", color=MUTED, size=11, weight="bold")
    cols = [(h, ok) for h, ok in (("return", bool(cost)), ("R", bool(risk)), ("$", show_money)) if ok]
    for k, (h, _) in enumerate(reversed(cols)):
        t(1138 - 96 * k, 468, h, color=MUTED, size=10, ha="right")
    y = 440
    for a in pos["alternatives"][:7]:
        actual = a["plan"] == "Actual"
        t(672, y, "What you did" if actual else card_label(a["plan"]), size=12, weight="bold" if actual else "normal")
        vals = [v for v, ok in ((pct_of(a["pnl"], cost), bool(cost)), (r_of(a["pnl"], risk), bool(risk)),
                                (money(a["pnl"]), show_money)) if ok]
        for k, v in enumerate(reversed(vals)):
            t(1138 - 96 * k, y, v, size=11.5, ha="right", family="monospace", weight="bold" if actual else "normal")
        y -= 38

    # the lesson, the thing to remember: full width, its own band
    if args.lesson:
        box(40, 30, 1120, 100, "#18213a", 10)
        ax.add_patch(plt.Rectangle((40, 30), 6, 100, color=GOOD))
        t(66, 118, "LESSON", color=GOOD, size=11, weight="bold")
        for k, ln in enumerate(textwrap.wrap(args.lesson, 88)[:2]):
            t(66, 94 - k * 30, ln, size=19, weight="bold")
    t(1160, 8, "TheStrat review · 5m / 15m / 30m / 60m · not advice", color=MUTED, size=9, ha="right", va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True, help="Folder strat_review.py wrote (has review.json)")
    ap.add_argument("--lesson", help="One sentence: the lesson, in the trader's words if possible")
    ap.add_argument("--notes", help="Optional extra line, e.g. what you would do next time")
    ap.add_argument("--handle", help="Optional name or @handle to show")
    ap.add_argument("--setup", help="Type of trade and primary timeframe/combo, e.g. 'Reversal · 30m F2d-2u'")
    ap.add_argument("--no-dollars", "--r-only", dest="no_dollars", action="store_true",
                    help="Show % and R only, no dollar amounts")
    ap.add_argument("--good", "--pro", dest="good", action="append",
                    help="A good call, one line (repeatable; with --bad, replaces the drafted checklist)")
    ap.add_argument("--bad", "--con", dest="bad", action="append",
                    help="A bad call, one line (repeatable; with --good, replaces the drafted checklist)")
    ap.add_argument("--position", type=int, help="Which position to share (1-based); default the largest")
    args = ap.parse_args(argv)

    folder = Path(args.review)
    rep = json.loads((folder / "review.json").read_text())
    if not rep.get("positions"):
        raise SystemExit("review.json has no positions")
    pos = rep["positions"][args.position - 1] if args.position else main_position(rep)
    out = folder / "share"
    out.mkdir(exist_ok=True)
    checks = custom_checks(args.good, args.bad) if (args.good or args.bad) else strat_checks(rep, pos)
    text = build_text(rep, pos, args, checks)
    (out / "post.md").write_text(text + "\n")
    made = ["post.md"]
    if pos.get("timeframes_chart") and (folder / pos["timeframes_chart"]).exists():
        shutil.copy(folder / pos["timeframes_chart"], out / "timeframes.png")
        made.append("timeframes.png")
    try:
        card(out / "card.png", rep, pos, args, checks)
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
