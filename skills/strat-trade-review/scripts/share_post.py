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


def chart_facts(rep: dict, pos: dict) -> list[dict]:
    """What the chart said at each decision, as facts. Nothing here is graded: whether entering against
    continuity was right depends on the setup (only an exhaustion reversal justifies it), so the facts
    name the setup next to the continuity and leave the judgement to the review and the trader."""
    bull = pos["direction"] == "BULL"
    tfs = pos.get("tfs") or [tf for tf in pos["fills"][0]["states"] if tf != "D"]
    side0 = pos["fills"][0]["side"]
    entries = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] == side0]
    exits = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] != side0]
    broke, failed = ("2u", "F2u") if bull else ("2d", "F2d")
    away = "below" if bull else "above"
    facts = []

    # context: the open, and Monday's week/day coupling
    lv = pos.get("levels") or {}
    day0 = datetime.fromisoformat(pos["fills"][0]["time"])
    ctx = []
    if lv.get("day open") and lv.get("prior close (gap fill)"):
        gap = lv["day open"] / lv["prior close (gap fill)"] - 1
        if abs(gap) >= 0.002:
            ctx.append(f"gap {'up' if gap > 0 else 'down'} {abs(gap):.1%} from the prior close")
    if day0.weekday() == 0:
        ctx.append("Monday: the week and the day are the same candle")
    if ctx:
        facts.append(dict(name="Context", detail="; ".join(ctx)))

    # the entry: which trigger, was it holding, what continuity said
    n1, f1 = entries[0]
    t1_ = datetime.fromisoformat(f1["time"])
    e = setup_at(pos, t1_)
    st = f1["states"]
    if e:
        tok = cc_token(st.get(e["tf"], {}).get("combo", ""))
        status = (f"failing at the fill ({tok}, back inside)" if tok == failed
                  else "holding at the fill" if tok == broke else f"{tok} at the fill")
        facts.append(dict(name=f"#{n1} entry: {e['tf']} {e['combo']}, {e['family']}",
                          detail=f"trigger {e['trigger']:.2f}, C1 stop {e['stop_c1']:.2f}; {status}"))
    else:
        facts.append(dict(name=f"#{n1} entry: no trigger in the forming bar",
                          detail=f"no {broke} break on {'/'.join(tfs)} when filled"))
    against = [tf for tf in tfs if st.get(tf, {}).get("sign") is not None and st[tf]["sign"] != bull]
    if against:
        rev = e is not None and "Reversal" in e["family"]
        facts.append(dict(name=f"Continuity at #{n1}: {f1['continuity']}",
                          detail=f"{', '.join(against)} {away} their opens; "
                                 + ("a reversal; against continuity it needs exhaustion" if rev
                                    else "no reversal setup against them")))
    else:
        facts.append(dict(name=f"Continuity at #{n1}: {f1['continuity']}", detail=f"{', '.join(tfs)} agreed"))

    # adds
    for n, f in entries[1:]:
        ea = setup_at(pos, datetime.fromisoformat(f["time"]))
        worse = (f["price"] < f1["price"]) == (side0 == "BUY")
        facts.append(dict(name=f"#{n} add at {f['price']:g}, {'worse' if worse else 'better'} than #{n1}",
                          detail=(f"on a {ea['tf']} {ea['combo']} trigger {ea['trigger']:.2f}" if ea
                                  else "no new trigger; continuity " + f["continuity"])))

    # exits
    c = pos.get("clean") or {}
    t1 = pos.get("t1")
    if exits:
        ns = ", ".join(f"#{n}" for n, _ in exits)
        notes = []
        if c.get("time"):
            t0 = datetime.fromisoformat(c["time"])
            mins = timedelta(minutes=TF_MINUTES.get(c.get("tf"), 30))
            if any(t0 - mins <= datetime.fromisoformat(f["time"]) <= t0 + mins for _, f in exits):
                notes.append(f"on the {c['tf']} {c['event']} trigger bar, the clean entry")
        htf = [tf for tf in ("30m", "60m", "D") if tf in pos["fills"][0]["states"]]
        live = []
        for _, f in exits:
            for tf in htf:
                s_ = f["states"].get(tf, {})
                if s_.get("sign") == bull and cc_token(s_.get("combo", "")) in ((broke, "F2d") if bull else (broke, "F2u")):
                    live.append(f"{tf} {cc_token(s_['combo'])}")
        if live:
            notes.append(f"with the {', '.join(dict.fromkeys(live))} still in force")
        if t1 is not None:
            reached = any(f.get("underlying") is not None and ((f["underlying"] >= t1) if bull else (f["underlying"] <= t1))
                          for _, f in exits)
            notes.append(f"{'at or past' if reached else 'before'} T1 {t1:.2f}")
        facts.append(dict(name=f"Exit {ns}", detail="; ".join(notes)))
    return facts


def rule_results(rep: dict, pos: dict, rules: dict) -> list[dict]:
    """The trader's own rules, from their rules file, each kept or broken. Only rules they set."""
    out = []
    side0 = pos["fills"][0]["side"]
    entries = [(n, f) for n, f in enumerate(pos["fills"], 1) if f["side"] == side0]
    lim = rules.get("max_daily_loss") or rep.get("max_daily_loss")
    dw = rep.get("day_worst")
    if rules.get("max_daily_loss") and dw:
        used = abs(min(dw["pnl"], 0)) / abs(lim)
        out.append(dict(ok=used < 1, name=f"Daily loss limit ${abs(lim):,.0f}",
                        detail=f"worst point {money(dw['pnl'])}, {used:.0%} of it"))
    if rules.get("no_averaging_down"):
        worse = [n for n, f in entries[1:] if (f["price"] < entries[0][1]["price"]) == (side0 == "BUY")]
        out.append(dict(ok=not worse, name="No averaging down",
                        detail=f"#{', #'.join(map(str, worse))} added at a worse price" if worse else "no adds at a worse price"))
    if rules.get("no_entries_before"):
        cut = rules["no_entries_before"]
        early = [n for n, f in entries if datetime.fromisoformat(f["time"]).strftime("%H:%M") < cut]
        out.append(dict(ok=not early, name=f"No entries before {cut} ET",
                        detail=f"#{', #'.join(map(str, early))} before it" if early else "first entry after it"))
    if rules.get("max_entries"):
        k = int(rules["max_entries"])
        out.append(dict(ok=len(entries) <= k, name=f"At most {k} entries per trade", detail=f"{len(entries)} entries"))
    for r in rules.get("other", []):     # rules the data can't check: listed for the trader to answer
        out.append(dict(ok=None, name=r, detail=""))
    return out


def custom_rules(kept: list[str] | None, broke: list[str] | None) -> list[dict]:
    return ([dict(ok=True, name=g, detail="") for g in kept or []]
            + [dict(ok=False, name=b, detail="") for b in broke or []])


def main_position(rep: dict) -> dict:
    return max(rep["positions"], key=lambda p: abs(p["qty"] * (p.get("avg_entry") or 0)))


def first_fill_context(pos: dict) -> tuple[str, str]:
    f = pos["fills"][0]
    cells = [f"{tf} {st['combo']}{'' if st.get('sign') is None else (' +' if st['sign'] else ' -')}"
             for tf, st in f["states"].items()]
    return f["continuity"], " | ".join(cells)


def build_text(rep: dict, pos: dict, args, facts: list[dict], rules: list[dict]) -> str:
    risk = (pos.get("clean") or {}).get("risk")
    cost = pos.get("cost") if pos["asset"] != "future" else None
    show_money = not args.no_dollars
    day = date.fromisoformat(rep.get("trade_date") or pos["fills"][0]["time"][:10])
    arrow = "🟢 BULL" if pos["direction"] == "BULL" else "🔴 BEAR"
    head, rest = result_parts(pos, show_money)
    unit = "contracts" if pos["asset"] != "stock" else "shares"
    lines = [f"**{pos['label']} · {day:%b %-d, %Y}** · {arrow}" + (f" · {args.handle}" if args.handle else "")]
    if args.setup:
        lines.append(f"**Setup:** {args.setup}")
    lines += [f"**Result: {head}**"
              + (f" ({', '.join(rest)})" if rest else "") + f" on {pos['qty']:g} {unit}"]
    if args.lesson:
        lines.append(f"> **Reflection:** {args.lesson}")
    lines.append("**What the chart said**")
    lines += [f"• {x['name']}" + (f": {x['detail']}" if x["detail"] else "") for x in facts]
    if rules:
        kept = sum(1 for r in rules if r["ok"])
        graded = sum(1 for r in rules if r["ok"] is not None)
        lines.append(f"**My rules: kept {kept} of {graded}**")
        lines += [f"{'✓ Kept' if r['ok'] else ('✗ Broke' if r['ok'] is False else '? Your call')} · {r['name']}"
                  + (f": {r['detail']}" if r["detail"] else "") for r in rules]
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


def card(path: Path, rep: dict, pos: dict, args, facts: list[dict], rules: list[dict]) -> None:
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

    # what the chart said: facts at each decision, not graded
    t(40, 466, "WHAT THE CHART SAID", color=MUTED, size=11, weight="bold")
    y = 440
    shown = min(len(rules), 4)
    room = 5 if not rules else (4 if shown <= 4 else 3)
    # decisions first (entry, continuity, adds, exit); the context line only if there is room
    ordered = [x for x in facts if x["name"] != "Context" and not x["name"].startswith("Context")] + \
              [x for x in facts if x["name"].startswith("Context")]
    for x in ordered[:room]:
        ax.add_patch(Circle((50, y - 8), 3.5, fc=MUTED, ec="none"))
        t(64, y, x["name"], size=12, weight="bold")
        if x["detail"]:
            d = x["detail"] if len(x["detail"]) <= 78 else x["detail"][:77] + "…"
            t(64, y - 17, d, size=10, color=MUTED)
        y -= 38 if x["detail"] else 26

    # the trader's own rules, kept or broken, only when they set some
    if rules:
        kept = sum(1 for r in rules if r["ok"])
        graded = sum(1 for r in rules if r["ok"] is not None)
        y -= 6
        t(40, y, "MY RULES", color=MUTED, size=11, weight="bold")
        t(600, y, f"kept {kept} of {graded}", color=FG, size=11, weight="bold", ha="right")
        y -= 26
        for r in rules[:4]:
            col = GOOD if r["ok"] else (BAD if r["ok"] is False else MUTED)
            ax.add_patch(Circle((50, y - 8), 9, fc=col, ec="none"))
            t(50, y - 8, "✓" if r["ok"] else ("✗" if r["ok"] is False else "?"), ha="center", va="center",
              size=10, weight="bold", color=BG)
            t(66, y, r["name"] + (f"  ·  {r['detail']}" if r["detail"] else ""), size=11.5)
            t(600, y, "KEPT" if r["ok"] else ("BROKE" if r["ok"] is False else "YOUR CALL"), size=9.5, weight="bold",
              color=col, ha="right")
            y -= 25

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
        t(66, 118, "REFLECTION", color=GOOD, size=11, weight="bold")
        for k, ln in enumerate(textwrap.wrap(args.lesson, 78)[:2]):
            t(66, 94 - k * 30, ln, size=19, weight="bold")
    t(1160, 8, "TheStrat review · 5m / 15m / 30m / 60m · not advice", color=MUTED, size=9, ha="right", va="bottom")
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
    ap.add_argument("--no-dollars", "--r-only", dest="no_dollars", action="store_true",
                    help="Show % and R only, no dollar amounts")
    ap.add_argument("--rules", help="The trader's rules file (JSON, see assets/my-rules.json); default: my-rules.json "
                                    "in the review folder or the current folder, if present")
    ap.add_argument("--kept", action="append", help="A personal rule kept, one line (repeatable; replaces the rules file)")
    ap.add_argument("--broke", action="append", help="A personal rule broken, one line (repeatable; replaces the rules file)")
    ap.add_argument("--position", type=int, help="Which position to share (1-based); default the largest")
    args = ap.parse_args(argv)

    folder = Path(args.review)
    rep = json.loads((folder / "review.json").read_text())
    if not rep.get("positions"):
        raise SystemExit("review.json has no positions")
    pos = rep["positions"][args.position - 1] if args.position else main_position(rep)
    out = folder / "share"
    out.mkdir(exist_ok=True)
    facts = chart_facts(rep, pos)
    if args.kept or args.broke:
        rules = custom_rules(args.kept, args.broke)
    else:
        rp = next((p for p in ([Path(args.rules)] if args.rules else [folder / "my-rules.json", Path("my-rules.json")])
                   if p.exists()), None)
        rules = rule_results(rep, pos, json.loads(rp.read_text())) if rp else []
    text = build_text(rep, pos, args, facts, rules)
    (out / "post.md").write_text(text + "\n")
    made = ["post.md"]
    if pos.get("timeframes_chart") and (folder / pos["timeframes_chart"]).exists():
        shutil.copy(folder / pos["timeframes_chart"], out / "timeframes.png")
        made.append("timeframes.png")
    try:
        card(out / "card.png", rep, pos, args, facts, rules)
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
