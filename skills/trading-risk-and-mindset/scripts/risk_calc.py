#!/usr/bin/env python3
"""Position size, trade statistics in R, and risk of ruin. Stdlib only.

  size   how many shares, option contracts or futures contracts for a given risk
  stats  expectancy, win rate, streaks and drawdown from a list of R multiples
  ruin   Monte Carlo of drawdowns and ruin for a risk % per trade

Examples:
  risk_calc.py size --account 25000 --risk-pct 1 --entry 774.82 --stop 773.61
  risk_calc.py size --account 25000 --risk-pct 1 --option --premium 0.94 --underlying 774.82 \\
      --stop 773.61 --strike 775 --dte 0.2 --iv 0.18 --type call
  risk_calc.py size --account 25000 --risk-dollars 250 --entry 6500 --stop 6494 --point-value 5
  risk_calc.py stats --r trades.csv                (a column named r, R or r_multiple; or one number per line)
  risk_calc.py stats --r "1.9,-1,-1,0.5,2.4,-1.3"
  risk_calc.py ruin --r trades.csv --risk-pct 1 --trades 200
  risk_calc.py ruin --win-rate 0.45 --avg-win 1.5 --risk-pct 2 --trades 200
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from pathlib import Path


# ----------------------------------------------------------------------------- size

def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(S: float, K: float, T: float, vol: float, call: bool, r: float = 0.04) -> float:
    if T <= 0 or vol <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r + vol * vol / 2) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    if call:
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def cmd_size(a) -> None:
    budget = a.risk_dollars if a.risk_dollars else a.account * a.risk_pct / 100
    if a.option:
        if a.stop is None:
            per = a.premium * 100
            how = f"no stop: the whole premium {a.premium:.2f} x 100"
        else:
            call = a.type.lower().startswith("c")
            T = max(a.dte, 1e-4) / 365
            S0, S1 = a.underlying, a.stop
            model0 = bs_price(S0, a.strike, T, a.iv, call)
            model1 = bs_price(S1, a.strike, T, a.iv, call)
            at_stop = max(0.0, a.premium - (model0 - model1))   # shift the model move onto the real premium
            per = (a.premium - at_stop) * 100
            how = (f"premium {a.premium:.2f} now, about {at_stop:.2f} with the underlying at the stop {S1:g} "
                   f"(Black-Scholes, IV {a.iv:.0%}; an ESTIMATE, 0DTE can move more)")
        unit = "contracts"
    else:
        per = abs(a.entry - a.stop) * (a.point_value or 1)
        how = (f"{abs(a.entry - a.stop):g} points x ${a.point_value:g}/point" if a.point_value
               else f"{abs(a.entry - a.stop):.2f} per share")
        unit = "contracts" if a.point_value else "shares"
    if per <= 0:
        raise SystemExit("Risk per unit is zero: check entry and stop.")
    n = math.floor(budget / per)
    print(f"Risk budget (1R): ${budget:,.2f}")
    print(f"Risk per unit:    ${per:,.2f}  ({how})")
    if n < 1:
        print(f"Size: 0 {unit}. One unit risks ${per:,.2f}, more than 1R. Skip it, or use a smaller instrument "
              "(micro futures, a spread); don't tighten the stop to fit.")
        return
    print(f"Size: {n} {unit}, actual risk ${n * per:,.2f} ({n * per / budget:.2f}R of budget)")


# ----------------------------------------------------------------------------- stats

def load_r(spec: str) -> list[float]:
    p = Path(spec)
    if not p.exists():
        return [float(x) for x in spec.replace(";", ",").split(",") if x.strip()]
    text = p.read_text().strip().splitlines()
    head = [h.strip().lower() for h in text[0].split(",")]
    for key in ("r", "r_multiple", "r multiple", "rmultiple"):
        if key in head:
            col = head.index(key)
            return [float(row[col]) for row in csv.reader(text[1:]) if len(row) > col and row[col].strip()]
    return [float(line.split(",")[0]) for line in text if line.strip() and _isnum(line.split(",")[0])]


def _isnum(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def streaks_and_dd(rs: list[float]) -> tuple[int, int, float]:
    worst_loss_run = run = best_win_run = wrun = 0
    eq = peak = 0.0
    dd = 0.0
    for r in rs:
        if r < 0:
            run += 1
            wrun = 0
        else:
            wrun += 1
            run = 0
        worst_loss_run = max(worst_loss_run, run)
        best_win_run = max(best_win_run, wrun)
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return worst_loss_run, best_win_run, dd


def cmd_stats(a) -> None:
    rs = load_r(a.r)
    if not rs:
        raise SystemExit("No R values found.")
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    n = len(rs)
    wr = len(wins) / n
    aw = statistics.mean(wins) if wins else 0.0
    al = statistics.mean(losses) if losses else 0.0
    exp = statistics.mean(rs)
    lrun, wrun, dd = streaks_and_dd(rs)
    big = [r for r in losses if r < -1.05]
    print(f"Trades: {n}   Net: {sum(rs):+.1f}R   Expectancy: {exp:+.2f}R per trade")
    print(f"Win rate: {wr:.0%}   Average win: {aw:+.2f}R   Average loss: {al:+.2f}R"
          + (f"   Payoff ratio: {aw / abs(al):.2f}" if al else ""))
    print(f"Largest win: {max(rs):+.2f}R   Largest loss: {min(rs):+.2f}R")
    print(f"Longest losing streak: {lrun}   Longest winning streak: {wrun}   Max drawdown: {dd:.1f}R")
    if n > 1:
        sd = statistics.stdev(rs)
        print(f"Std dev: {sd:.2f}R   Expectancy / std dev: {exp / sd if sd else 0:.2f}"
              + ("   (fewer than 30 trades: treat all of this as a rough estimate)" if n < 30 else ""))
    if big:
        print(f"Losses past -1R: {len(big)} trades, {sum(big):+.1f}R total, {sum(r + 1 for r in big):+.1f}R "
              "of that beyond the planned stop. Honoring stops comes before any entry fix.")
    if wins and losses and aw < abs(al):
        print("Average win is smaller than the average loss: check for cutting winners early and holding losers.")


# ----------------------------------------------------------------------------- ruin

def cmd_ruin(a) -> None:
    if a.r:
        pool = load_r(a.r)
        draw = lambda rng: rng.choice(pool)
        src = f"resampling your {len(pool)} trades"
    else:
        draw = lambda rng: a.avg_win if rng.random() < a.win_rate else -a.avg_loss
        src = f"win rate {a.win_rate:.0%}, +{a.avg_win:g}R wins, -{a.avg_loss:g}R losses"
    rng = random.Random(a.seed)
    f = a.risk_pct / 100
    dds, ruined, ends, streaks = [], 0, [], []
    for _ in range(a.sims):
        eq = peak = 1.0
        worst = 0.0
        run = longest = 0
        for _ in range(a.trades):
            r = draw(rng)
            eq *= 1 + f * r
            run = run + 1 if r < 0 else 0
            longest = max(longest, run)
            peak = max(peak, eq)
            worst = min(worst, eq / peak - 1)
            if eq <= 1 - a.ruin_pct / 100:
                ruined += 1
                break
        dds.append(worst)
        ends.append(eq)
        streaks.append(longest)
    dds.sort()
    ends.sort()
    streaks.sort()
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
    print(f"{a.sims} runs of {a.trades} trades at {a.risk_pct:g}% risk per trade, {src}")
    print(f"Max drawdown: median {q(dds, 0.5):.0%}, 1 in 20 runs worse than {q(dds, 0.05):.0%}")
    print(f"Longest losing streak: median {q(streaks, 0.5)}, 1 in 20 runs {q(streaks, 0.95)} or more")
    print(f"Ending equity: median {q(ends, 0.5):.2f}x, 1 in 20 runs below {q(ends, 0.05):.2f}x")
    print(f"Runs that lost {a.ruin_pct:g}% of the account: {ruined / a.sims:.1%}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("size", help="Position size for a given risk")
    s.add_argument("--account", type=float, default=0)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--risk-pct", type=float, help="Percent of account to risk (1 = 1%%)")
    g.add_argument("--risk-dollars", type=float)
    s.add_argument("--entry", type=float, help="Entry price (shares, futures)")
    s.add_argument("--stop", type=float, help="Stop price (for options: the underlying's stop level)")
    s.add_argument("--point-value", type=float, help="Futures dollars per point (ES 50, MES 5, NQ 20, MNQ 2)")
    s.add_argument("--option", action="store_true")
    s.add_argument("--premium", type=float)
    s.add_argument("--underlying", type=float)
    s.add_argument("--strike", type=float)
    s.add_argument("--dte", type=float, default=1, help="Days to expiry (0.2 for a few hours of 0DTE)")
    s.add_argument("--iv", type=float, default=0.2, help="Implied volatility as a decimal")
    s.add_argument("--type", default="call")

    t = sub.add_parser("stats", help="Statistics from R multiples")
    t.add_argument("--r", required=True, help="CSV file with an r column, or comma-separated values")

    u = sub.add_parser("ruin", help="Monte Carlo drawdown and ruin")
    u.add_argument("--r", help="Your R multiples to resample (file or list)")
    u.add_argument("--win-rate", type=float, default=0.45)
    u.add_argument("--avg-win", type=float, default=1.5)
    u.add_argument("--avg-loss", type=float, default=1.0)
    u.add_argument("--risk-pct", type=float, default=1.0)
    u.add_argument("--trades", type=int, default=200)
    u.add_argument("--sims", type=int, default=5000)
    u.add_argument("--ruin-pct", type=float, default=50, help="Drawdown that counts as ruin, percent")
    u.add_argument("--seed", type=int, default=7)

    a = ap.parse_args(argv)
    if a.cmd == "size":
        if a.risk_pct is not None and not a.account:
            ap.error("--risk-pct needs --account")
        if a.option and (a.premium is None or (a.stop is not None and None in (a.underlying, a.strike))):
            ap.error("--option needs --premium, and with --stop also --underlying and --strike")
        if not a.option and (a.entry is None or a.stop is None):
            ap.error("need --entry and --stop")
        cmd_size(a)
    elif a.cmd == "stats":
        cmd_stats(a)
    else:
        cmd_ruin(a)


if __name__ == "__main__":
    main()
