#!/usr/bin/env python3
"""Turn a strat_review.py output folder into a post to share (Discord by default).

Writes, next to review.json:

  share/post.md     the message text, under Discord's 2,000 character limit, no tables
                    (Discord does not render Markdown tables; the alternatives go in a code block)
  share/card.png        a 1200x675 card shaped like a broker's P/L card: symbol, side, one big % (green gain,
                        red loss; R for futures), average in and out, no dollars and no size; then the Strat
                        scorecard (each decision with or against the chart), the state at entry, the
                        alternatives, and the trader's reflection
  share/timeframes.png  the 5m/15m/30m/60m chart with every fill numbered (the main image)
  share/chart.png       the single-timeframe session chart

Attach timeframes.png and card.png to the message. Personal goals and limits (daily loss limit, rules)
never go in the share; they belong in the trader's private journal. Dollars appear only in the text, and
only with --dollars.

  python3 share_post.py --review review_out --lesson "Wait for the 30m trigger." [--dollars] [--handle @me]
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


GOOD, BAD = "#5b9cff", "#f5a524"   # scorecard: with / against the Strat; never green and red, which mean bull and bear
GAIN, LOSS = BULL, BEAR             # the headline % only, as on a broker's P/L card: green gain, red loss


TF_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}


def setup_at(pos: dict, when: datetime) -> dict | None:
    """The trigger a fill at `when` was riding: the highest timeframe whose forming bar had broken in the
    trade's direction by then (a trigger inside the current bar of its timeframe)."""
    best = None
    for e in pos.get("triggers", []):
        if e["dir"] != pos["direction"] or e.get("gap") or e["tf"] not in TF_MINUTES:
            continue
        bar_start = datetime.fromisoformat(e["bar_start"])
        if bar_start <= when < bar_start + timedelta(minutes=TF_MINUTES[e["tf"]]) and \
                datetime.fromisoformat(e["time"]) <= when:
            if best is None or TF_MINUTES[e["tf"]] > TF_MINUTES[best["tf"]]:
                best = e
    return best


def context_notes(pos: dict) -> list[str]:
    """Not graded: the open's gap, and Monday, when the week and the day are the same candle."""
    lv = pos.get("levels") or {}
    out = []
    if lv.get("day open") and lv.get("prior close (gap fill)"):
        gap = lv["day open"] / lv["prior close (gap fill)"] - 1
        if abs(gap) >= 0.002:
            out.append(f"gap {'up' if gap > 0 else 'down'} {abs(gap):.1%}")
    if datetime.fromisoformat(pos["fills"][0]["time"]).weekday() == 0:
        out.append("Monday: week and day are the same candle")
    return out


def scorecard(pos: dict) -> list[dict]:
    """The Strat scorecard: each decision checked against the chart, nothing personal (no loss limits or
    goals; those stay in the trader's private journal). ok is True (with the chart), False (against it),
    or None (the chart doesn't decide it)."""
    bull = pos["direction"] == "BULL"
    tfs = pos.get("tfs") or [tf for tf in pos["fills"][0]["states"] if tf != "D"]
    side0 = pos["fills"][0]["side"]
    entries = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] == side0]
    exits = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] != side0]
    broke, failed = ("2u", "F2u") if bull else ("2d", "F2d")
    away = "below" if bull else "above"
    items = []

    # entry: on a trigger in the forming bar, and still live when filled
    n1, f1 = entries[0]
    e = setup_at(pos, datetime.fromisoformat(f1["time"]))
    st = f1["states"]
    if e:
        tok = cc_token(st.get(e["tf"], {}).get("combo", ""))
        live = tok != failed
        items.append(dict(ok=live, name="Entered on a live trigger" if live else "Entered on a failing trigger",
                          detail=f"#{n1}: {e['tf']} {e['combo']} {e['trigger']:.2f}, C1 {e['stop_c1']:.2f}"
                                 + ("" if live else f"; {e['tf']} back inside ({tok}) at the fill")))
    else:
        items.append(dict(ok=False, name="Entered without a trigger",
                          detail=f"#{n1}: no {broke} break on {'/'.join(tfs)} when filled"))

    # continuity: with it, or against it only on a reversal (exhaustion)
    against = [tf for tf in tfs if st.get(tf, {}).get("sign") is not None and st[tf]["sign"] != bull]
    if not against:
        items.append(dict(ok=True, name="With continuity", detail=f"{f1['continuity']}: {', '.join(tfs)} agreed"))
    elif e is not None and "Reversal" in e["family"]:
        items.append(dict(ok=True, name="Against continuity on a reversal",
                          detail=f"{', '.join(against)} {away} their opens; valid only as an exhaustion reversal"))
    else:
        items.append(dict(ok=False, name="Against continuity, no reversal",
                          detail=f"{', '.join(against)} {away} their opens"))

    # adds: each on a new trigger
    if entries[1:]:
        bare = []
        for n, f in entries[1:]:
            if not setup_at(pos, datetime.fromisoformat(f["time"])):
                bare.append(n)
        items.append(dict(ok=not bare, name="Added on new triggers" if not bare else "Added without a trigger",
                          detail=(f"#{', #'.join(map(str, bare))}: no new trigger" if bare
                                  else f"{len(entries) - 1} add{'s' if len(entries) > 2 else ''}, each on a trigger")))

    # exit: at the target, or with nothing still in force for the trade
    if exits:
        ns = ", ".join(f"#{n}" for n, _ in exits)
        t1 = pos.get("t1")
        reached = t1 is not None and any(f.get("underlying") is not None and
                                         ((f["underlying"] >= t1) if bull else (f["underlying"] <= t1)) for _, f in exits)
        live = []
        for _, f in exits:
            for tf in ("30m", "60m", "D"):
                s_ = f["states"].get(tf, {})
                if s_.get("sign") == bull and cc_token(s_.get("combo", "")) in (broke, "F2d" if bull else "F2u"):
                    live.append(f"{tf} {cc_token(s_['combo'])}")
        live = list(dict.fromkeys(live))
        fresh = [x for x in (setup_at(pos, datetime.fromisoformat(f["time"])) for _, f in exits) if x]
        if fresh:   # a trigger in the trade's direction fired in the bar they sold in
            x = max(fresh, key=lambda e: TF_MINUTES[e["tf"]])
            live.insert(0, f"{x['tf']} {x['combo']} trigger {x['trigger']:.2f}")
        if reached:
            items.append(dict(ok=True, name="Exited at the target", detail=f"{ns} at or past T1 {t1:.2f}"))
        elif live:
            items.append(dict(ok=False, name="Exited with signals in force",
                              detail=f"{ns}: {', '.join(live)} still in force" + (f", before T1 {t1:.2f}" if t1 else "")))
        else:
            items.append(dict(ok=None, name="Exited before the target",
                              detail=f"{ns}: before T1 {t1:.2f}, no higher-timeframe signal in force" if t1
                              else f"{ns}: no higher-timeframe signal in force"))
    return items


def main_position(rep: dict) -> dict:
    return max(rep["positions"], key=lambda p: abs(p["qty"] * (p.get("avg_entry") or 0)))


def first_fill_context(pos: dict) -> tuple[str, str]:
    f = pos["fills"][0]
    cells = [f"{tf} {st['combo']}{'' if st.get('sign') is None else (' +' if st['sign'] else ' -')}"
             for tf, st in f["states"].items()]
    return f["continuity"], " | ".join(cells)


def score_line(items: list[dict]) -> str:
    graded = [i for i in items if i["ok"] is not None]
    return f"{sum(1 for i in graded if i['ok'])} of {len(graded)}"


def mark(ok) -> str:
    return "✓" if ok else ("✗" if ok is False else "–")


def build_text(rep: dict, pos: dict, args, items: list[dict]) -> str:
    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    arrow = "🟢 BULL" if pos["direction"] == "BULL" else "🔴 BEAR"
    head, rest = result_parts(pos, args.dollars)
    lines = [f"**{pos['label']} · {day:%b %-d, %Y}** · {arrow}" + (f" · {args.handle}" if args.handle else "")]
    if args.setup:
        lines.append(f"**Setup:** {args.setup}")
    lines.append(f"**{head}**" + (f" ({', '.join(rest)})" if rest else ""))
    if args.lesson:
        lines.append(f"> {args.lesson}")
    ctx = context_notes(pos)
    lines.append(f"**Strat scorecard: {score_line(items)}**" + (f" _({'; '.join(ctx)})_" if ctx else ""))
    lines += [f"{mark(i['ok'])} {i['name']}: {i['detail']}" for i in items]
    c = pos.get("clean")
    if c and c.get("trigger"):
        lines.append(f"**Clean Strat:** {c['tf']} {c['event']} trigger {c['trigger']:.2f}, C1 {c['stop_c1']:.2f}"
                     f" → {pct_of(c['pnl'], cost) or r_of(c['pnl'], risk)}"
                     + (f", {r_of(c['pnl'], risk)}" if cost and risk else ""))
    rows = []
    for a in pos["alternatives"]:
        cells = [x for x in (pct_of(a["pnl"], cost), r_of(a["pnl"], risk)) if x]
        if args.dollars or not cells:
            cells.append(money(a["pnl"]))
        rows.append(f"{short_plan(a['plan']):<40}" + "".join(f"{x:>9}" for x in cells))
    foot = []
    if any("estimate" in a["source"].lower() or "black" in a["source"].lower() for a in pos["alternatives"]):
        foot.append("_Option alternatives are Black-Scholes estimates, not real marks._")
    if args.notes:
        foot.append(args.notes)
    foot.append("_TheStrat review on 5m/15m/30m/60m. Not advice._")
    text = "\n".join(lines + ["```", *rows, "```"] + foot)
    while len(text) > DISCORD_LIMIT and len(rows) > 2:   # keep Actual and Clean Strat, drop the middle
        rows.pop(-2)
        text = "\n".join(lines + ["```", *rows, "```"] + foot)
    return text


def card(path: Path, rep: dict, pos: dict, args, items: list[dict]) -> None:
    """A share card shaped like a broker's P/L card (symbol, side, one big % in gain/loss color, average in
    and out, no dollars, no size), with the Strat scorecard in place of a referral code."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch
    matplotlib.rcParams["text.parse_math"] = False

    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
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

    # header: symbol, side, date and setup
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    bull = pos["direction"] == "BULL"
    title = t(40, 642, pos["label"], size=26, weight="bold")
    fig.canvas.draw()
    bb = title.get_window_extent().transformed(ax.transData.inverted())
    box(bb.x1 + 16, 610, 92, 30, BULL if bull else BEAR, 6)
    t(bb.x1 + 62, 625, "▲ BULL" if bull else "▼ BEAR", ha="center", va="center", size=12, weight="bold", color=BG)
    t(40, 600, f"{day:%a %b %-d, %Y}" + (f"   ·   {args.setup}" if args.setup else "")
      + (f"   ·   {args.handle}" if args.handle else ""), color=MUTED, size=13)

    # the number: % on what was paid (R for futures), in gain/loss color like a broker's P/L card
    head, rest = result_parts(pos, False)
    pnl = pos["pnl"]
    t(34, 584, head, size=80, weight="bold", color=GAIN if pnl > 0 else (LOSS if pnl < 0 else FG))
    sub = rest[:]
    if pos.get("avg_entry") and pos.get("avg_exit"):
        sub.append(f"avg in {pos['avg_entry']:.2f}  →  out {pos['avg_exit']:.2f}")
    t(40, 448, "   ·   ".join(sub), color=MUTED, size=14)

    # the Strat scorecard
    t(40, 408, "STRAT SCORECARD", color=MUTED, size=11, weight="bold")
    t(600, 410, score_line(items), color=FG, size=13, weight="bold", ha="right", va="top")
    ctx = context_notes(pos)
    y = 382
    if ctx:
        t(40, y + 2, "Context: " + "  ·  ".join(ctx), color=MUTED, size=10, style="italic")
        y -= 22
    for i in items[:5]:
        col = GOOD if i["ok"] else (BAD if i["ok"] is False else MUTED)
        ax.add_patch(Circle((50, y - 9), 10, fc=col, ec="none"))
        t(50, y - 9, mark(i["ok"]), ha="center", va="center", size=11, weight="bold", color=BG)
        t(70, y, i["name"], size=13, weight="bold")
        t(600, y, "WITH" if i["ok"] else ("AGAINST" if i["ok"] is False else "JUDGMENT"), size=9.5,
          weight="bold", color=col, ha="right")
        d = i["detail"] if len(i["detail"]) <= 76 else i["detail"][:75] + "…"
        t(70, y - 19, d, size=10.5, color=MUTED)
        y -= 44

    # right panel: state at entry, then the alternatives (% and R only)
    box(650, 150, 510, 432, PANEL)
    f0 = pos["fills"][0]
    t(672, 562, "AT ENTRY #1", color=MUTED, size=11, weight="bold")
    t(1138, 562, f0["continuity"], color=FG, size=11, weight="bold", ha="right")
    for k, (tf, st) in enumerate(f0["states"].items()):
        x = 672 + k * 96
        sign = st.get("sign")
        t(x, 534, tf + (" ctx" if tf == "D" else ""), size=10, color=MUTED)
        t(x, 514, st["combo"].replace("-(new)", "-new") + ("" if sign is None else (" ↑" if sign else " ↓")),
          size=11, family="monospace", color=FG if sign is None else (BULL if sign else BEAR))
    ax.plot([672, 1138], [482, 482], color="#2a2a2a", linewidth=1)
    t(672, 468, "IF YOU HAD", color=MUTED, size=11, weight="bold")
    cols = [h for h, ok in (("return", bool(cost)), ("R", bool(risk))) if ok] or ["$"]
    for k, h in enumerate(reversed(cols)):
        t(1138 - 110 * k, 468, h, color=MUTED, size=10, ha="right")
    y = 440
    for a in pos["alternatives"][:7]:
        actual = a["plan"] == "Actual"
        t(672, y, "What you did" if actual else card_label(a["plan"]), size=12, weight="bold" if actual else "normal")
        vals = [v for v in (pct_of(a["pnl"], cost), r_of(a["pnl"], risk)) if v] or [money(a["pnl"])]
        for k, v in enumerate(reversed(vals)):
            t(1138 - 110 * k, y, v, size=12, ha="right", family="monospace", weight="bold" if actual else "normal")
        y -= 38

    # the trader's reflection, in their words
    if args.lesson:
        box(40, 30, 1120, 100, "#18213a", 10)
        ax.add_patch(plt.Rectangle((40, 30), 6, 100, color=GOOD))
        t(66, 118, "REFLECTION", color=GOOD, size=11, weight="bold")
        for k, ln in enumerate(textwrap.wrap(args.lesson, 78)[:2]):
            t(66, 94 - k * 30, ln, size=19, weight="bold")
    t(1160, 8, "TheStrat scorecard · 5m / 15m / 30m / 60m · not advice", color=MUTED, size=9, ha="right", va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True, help="Folder strat_review.py wrote (has review.json)")
    ap.add_argument("--lesson", "--reflection", dest="lesson",
                    help="The trader's reflection, one or two sentences in their words")
    ap.add_argument("--notes", help="Optional extra line, e.g. what you would do next time")
    ap.add_argument("--handle", help="Optional name or @handle to show")
    ap.add_argument("--setup", help="Type of trade and primary timeframe/combo, e.g. 'Reversal · 30m F2d-2u'")
    ap.add_argument("--dollars", action="store_true",
                    help="Also show dollar amounts in the post text (the card never shows dollars or size)")
    ap.add_argument("--no-dollars", "--r-only", action="store_true", help=argparse.SUPPRESS)  # the default now
    ap.add_argument("--position", type=int, help="Which position to share (1-based); default the largest")
    args = ap.parse_args(argv)

    folder = Path(args.review)
    rep = json.loads((folder / "review.json").read_text())
    if not rep.get("positions"):
        raise SystemExit("review.json has no positions")
    pos = rep["positions"][args.position - 1] if args.position else main_position(rep)
    out = folder / "share"
    out.mkdir(exist_ok=True)
    items = scorecard(pos)
    text = build_text(rep, pos, args, items)
    (out / "post.md").write_text(text + "\n")
    made = ["post.md"]
    if pos.get("timeframes_chart") and (folder / pos["timeframes_chart"]).exists():
        shutil.copy(folder / pos["timeframes_chart"], out / "timeframes.png")
        made.append("timeframes.png")
    try:
        card(out / "card.png", rep, pos, args, items)
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
