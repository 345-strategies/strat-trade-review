#!/usr/bin/env python3
"""TheStrat trade review: line up broker fills against multi-timeframe price action.

Reads a fills file (any broker, normalized to a few columns) and intraday bars for
the underlying, then reports for every position:

  * every leg, with the underlying price at the fill
  * TheStrat bar state (C2 / C1 / forming CC) on 5m, 15m, 30m and 60m at each fill, Day for context
  * Full Timeframe Continuity across those four (close vs open, sign channel only) at each fill
  * every 2u / 2d trigger of the session on each timeframe, with its stop,
    magnitude and what happened next (target first or stop first, in R)
  * reference levels (open, prior close, prior day high/low, opening range, HOD/LOD)
  * execution flags (scaled in, averaged down, against continuity, early session)
  * priced alternatives: hold, runner, scale out at T1, and a "clean Strat" version
    entered on the trigger, using real contract bars when given, otherwise a
    Black-Scholes estimate calibrated to your own fill prices (labeled ESTIMATE)
  * a chart PNG (optional, needs matplotlib)

Bar classification follows TheStrat Suite v3.1.x / TheStratGrammar SPEC:
  equal is not a break; gaps get no type; 2u/2d name the broken side, not the color;
  a 2u/2d that closes back inside the prior range is a Failing 2 (F2u / F2d, Reclaim
  method); a close exactly at the open counts as NOT above.

Stdlib only for the analysis. Optional: matplotlib (chart), yfinance (--fetch yfinance).
Run with -h for options. Times print in --display-tz with ET in parentheses.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Suite v3.1.1 bar-type palette (getBarTypeColor). Green/red are bull/bear, never good/bad.
SUITE_COLORS = {
    "1u": "#ffeb3b", "1d": "#ff9800",
    "2u": "#4caf50", "2d": "#f23645",
    "F2u": "#f77c80", "F2d": "#81c784",
    "3u": "#089981", "3d": "#e91e63",
}

# Contract multiplier and display tick for common futures roots. Override with --multiplier.
FUTURES = {
    "ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "RTY": 50, "M2K": 5, "YM": 5, "MYM": 0.5,
    "CL": 1000, "MCL": 100, "NG": 10000, "GC": 100, "MGC": 10, "SI": 5000, "SIL": 1000,
    "HG": 25000, "ZB": 1000, "ZN": 1000, "ZF": 1000, "ZT": 2000, "6E": 125000,
    "BTC": 5, "MBT": 0.1, "ETH": 50, "MET": 0.1,
}
FUT_MONTHS = "FGHJKMNQUVXZ"


# ----------------------------------------------------------------------------- time

def parse_time(s: str, default_tz=ET) -> datetime:
    s = str(s).strip()
    if re.fullmatch(r"\d{9,13}(\.\d+)?", s):
        v = float(s)
        if v > 1e11:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    tz = None
    m = re.search(r"\s*\b(ET|EST|EDT|PT|PST|PDT|CT|CST|CDT|UTC|GMT)$", s, re.I)
    if m:
        tz = {"ET": ET, "EST": ET, "EDT": ET,
              "PT": ZoneInfo("America/Los_Angeles"), "PST": ZoneInfo("America/Los_Angeles"),
              "PDT": ZoneInfo("America/Los_Angeles"),
              "CT": ZoneInfo("America/Chicago"), "CST": ZoneInfo("America/Chicago"),
              "CDT": ZoneInfo("America/Chicago"),
              "UTC": timezone.utc, "GMT": timezone.utc}[m.group(1).upper()]
        s = s[: m.start()].strip()
    s = s.replace("Z", "+00:00") if s.endswith("Z") else s
    dt = None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M",
                    "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p",
                    "%m/%d/%Y %I:%M %p", "%Y%m%d %H:%M:%S", "%Y%m%d;%H%M%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                pass
    if dt is None:
        raise ValueError(f"unrecognized time: {s!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz or default_tz)
    return dt


class Clock:
    def __init__(self, display_tz: str):
        self.tz = ZoneInfo(display_tz)
        self.abbr = {"America/Los_Angeles": "PT", "America/New_York": "ET",
                     "America/Chicago": "CT", "America/Denver": "MT", "UTC": "UTC"}.get(display_tz, display_tz)

    def fmt(self, t: datetime | None, with_date=False) -> str:
        if t is None:
            return "-"
        a = t.astimezone(self.tz)
        e = t.astimezone(ET)
        # outside regular hours, add the date and am/pm so overnight futures fills read unambiguously
        ext = with_date or not (time(9, 0) <= e.time() <= time(16, 15))
        f = "%b %d %-I:%M %p" if ext else "%-I:%M"
        g = "%-I:%M %p" if ext else "%-I:%M"
        if self.abbr == "ET":
            return e.strftime(f) + " ET"
        return f"{a.strftime(f)} {self.abbr} ({e.strftime(g)} ET)"


# ----------------------------------------------------------------------------- bars

@dataclass
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    end: datetime | None = None

    def merge(self, b: "Bar") -> None:
        self.high = max(self.high, b.high)
        self.low = min(self.low, b.low)
        self.close = b.close
        self.end = b.end


def _num(x):
    return float(str(x).replace(",", "").replace("$", "").strip())


ALIASES = {
    "time": ["time", "timestamp", "datetime", "date", "t", "date/time", "bar time"],
    "open": ["open", "o"], "high": ["high", "h"], "low": ["low", "l"], "close": ["close", "c", "last"],
}


def _pick(row: dict, key: str):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for a in ALIASES[key]:
        if a in low and low[a] not in (None, ""):
            return low[a]
    raise KeyError(key)


def load_bars(path: str) -> list[Bar]:
    p = Path(path)
    text = p.read_text()
    bars: list[Bar] = []
    if p.suffix.lower() == ".json" or text.lstrip().startswith(("{", "[")):
        data = json.loads(text)
        if isinstance(data, dict) and "result" in data and isinstance(data["result"], str):
            data = json.loads(data["result"])  # Public MCP get_price_history wrapper
        if isinstance(data, dict) and "regularMarket" in data:  # Public
            rows = []
            for sess in ("preMarket", "regularMarket", "afterMarket"):
                rows += data.get(sess, {}).get("bars", [])
            for r in rows:
                bars.append(Bar(parse_time(r["timestamp"]), _num(r["open"]), _num(r["high"]),
                                _num(r["low"]), _num(r["close"])))
        else:
            if isinstance(data, dict) and "bars" in data:
                data = data["bars"]
            if isinstance(data, dict) and "t" in data:  # columns format
                data = [dict(t=data["t"][i], o=data["o"][i], h=data["h"][i], l=data["l"][i], c=data["c"][i])
                        for i in range(len(data["t"]))]
            for r in data:
                bars.append(Bar(parse_time(_pick(r, "time")), _num(_pick(r, "open")), _num(_pick(r, "high")),
                                _num(_pick(r, "low")), _num(_pick(r, "close"))))
    else:
        for r in csv.DictReader(text.splitlines()):
            try:
                bars.append(Bar(parse_time(_pick(r, "time")), _num(_pick(r, "open")), _num(_pick(r, "high")),
                                _num(_pick(r, "low")), _num(_pick(r, "close"))))
            except (KeyError, ValueError):
                continue
    bars = [b for b in bars if not (b.high == b.low == b.open == b.close and b.start.second)]  # drop live stubs
    bars.sort(key=lambda b: b.start)
    if len(bars) >= 2:
        step = min((b2.start - b1.start) for b1, b2 in zip(bars, bars[1:]) if b2.start > b1.start)
    else:
        step = timedelta(minutes=5)
    for b in bars:
        b.end = b.start + step
    return bars


def fetch_yfinance(symbol: str, day: date, interval: str, out: Path, strict: bool = True,
                   days_back: int = 6) -> Path | None:
    def fail(msg):
        if strict:
            sys.exit(msg)
        print(f"note: {msg}", file=sys.stderr)
        return None
    try:
        import yfinance as yf  # noqa: WPS433
    except ImportError:
        return fail("yfinance is not installed: python3 -m pip install yfinance (or pass --bars)")
    try:
        df = yf.download(symbol, start=day - timedelta(days=days_back), end=day + timedelta(days=1),
                         interval=interval, prepost=False, progress=False, auto_adjust=False)
    except Exception as e:  # network, rate limit
        return fail(f"yfinance download failed for {symbol}: {e}")
    if df is None or df.empty:
        return fail(f"yfinance returned no {interval} bars for {symbol} around {day}. "
                    "1m data only reaches back ~30 days and 5m/15m ~60 days.")
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close"])
        for ts, r in df.iterrows():
            w.writerow([ts.isoformat(), r["Open"], r["High"], r["Low"], r["Close"]])
    return out


YF_FUTURES = {"ES": "ES=F", "MES": "ES=F", "NQ": "NQ=F", "MNQ": "NQ=F", "RTY": "RTY=F", "M2K": "RTY=F",
              "YM": "YM=F", "MYM": "YM=F", "CL": "CL=F", "MCL": "CL=F", "GC": "GC=F", "MGC": "GC=F",
              "SI": "SI=F", "SIL": "SI=F"}


def ensure_context(bars, daily, positions, sess, args, out: Path):
    """Fill in what the Strat state needs when the given bars stop short: the previous session's
    intraday bars and a few prior daily bars. Tries yfinance; otherwise the review notes the gap."""
    first = min(p.fills[0].time for p in positions)
    s0 = sess.start_of(first)
    has_prior = any(sess.start_of(b.start) < s0 and sess.contains(b.start) for b in bars)
    if has_prior and daily:
        return bars, daily
    inst = positions[0].inst
    sym = args.yf_symbol or (YF_FUTURES.get(inst.underlying, f"{inst.underlying}=F") if inst.asset == "future"
                             else inst.underlying)
    day = first.astimezone(ET).date()
    if not has_prior:
        step = min(((b.end - b.start) for b in bars), default=timedelta(minutes=5))
        interval = "1m" if step <= timedelta(minutes=1) else "5m"
        p = fetch_yfinance(sym, day, interval, out / f"context_{sym.replace('=', '_')}_{interval}.csv", strict=False)
        if p:
            extra = [b for b in load_bars(str(p)) if b.start < bars[0].start]
            if extra:
                bars = extra + bars
                print(f"Added {len(extra)} prior-session {interval} bars for {sym} from Yahoo Finance.", file=sys.stderr)
    if not daily:
        p = fetch_yfinance(sym, day, "1d", out / f"context_{sym.replace('=', '_')}_1d.csv", strict=False, days_back=10)
        if p:
            daily = load_bars(str(p))
            print(f"Added {len(daily)} daily bars for {sym} from Yahoo Finance.", file=sys.stderr)
    return bars, daily


# ----------------------------------------------------------------------------- instruments

@dataclass
class Instrument:
    symbol: str
    asset: str            # option | stock | future
    underlying: str
    multiplier: float
    cp: str | None = None  # C / P
    strike: float | None = None
    expiration: date | None = None

    def label(self) -> str:
        if self.asset == "option":
            return f"{self.underlying} {self.expiration:%b %d} {self.strike:g}{self.cp}"
        return self.symbol


def parse_instrument(sym: str, asset_hint: str | None, mult_override: float | None) -> Instrument:
    s = sym.strip().upper().lstrip("./")
    m = re.fullmatch(r"([A-Z]{1,6})\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})", s.replace(" ", ""))
    if m:
        root, yy, mm, dd, cp, k = m.groups()
        return Instrument(sym, "option", root, mult_override or 100, cp, int(k) / 1000.0,
                          date(2000 + int(yy), int(mm), int(dd)))
    m = re.fullmatch(r"([A-Z]{1,6})\s*(\d{6})([CP])([\d.]+)", s)  # Schwab .SPY261007C775
    if m:
        root, ymd, cp, k = m.groups()
        return Instrument(sym, "option", root, mult_override or 100, cp, float(k),
                          date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:])))
    m = re.fullmatch(r"([A-Z]{1,6})\s+(\d{1,2})/(\d{1,2})/(\d{2,4})\s+\$?([\d.]+)\s*(C|P|CALL|PUT)", s)
    if m:
        root, mo, dd, yy, k, cp = m.groups()
        yy = int(yy) + (2000 if len(yy) == 2 else 0)
        return Instrument(sym, "option", root, mult_override or 100, cp[0], float(k), date(yy, int(mo), int(dd)))
    m = re.fullmatch(r"([A-Z0-9]{1,4})\s+(\d{2})-(\d{2})", s)  # NinjaTrader "ES 12-26"
    if m and (m.group(1) in FUTURES or asset_hint == "future"):
        return Instrument(sym, "future", m.group(1), mult_override or FUTURES.get(m.group(1), 1))
    if asset_hint != "stock":
        m = re.fullmatch(r"([A-Z0-9]{1,4}?)([%s])(\d{1,2})" % FUT_MONTHS, s.replace(" ", ""))
        if m and (m.group(1) in FUTURES or asset_hint == "future"):
            return Instrument(sym, "future", m.group(1), mult_override or FUTURES.get(m.group(1), 1))
        if s.rstrip("!1") in FUTURES or asset_hint == "future":
            root = re.sub(r"[^A-Z0-9]", "", s.rstrip("!1"))
            return Instrument(sym, "future", root, mult_override or FUTURES.get(root, 1))
    return Instrument(sym, "stock", s, mult_override or 1)


# ----------------------------------------------------------------------------- fills & positions

BUY_WORDS = {"BUY", "BOT", "B", "BTO", "BTC", "BUY_TO_OPEN", "BUY_TO_CLOSE", "BUY TO OPEN",
             "BUY TO CLOSE", "BOUGHT", "LONG", "COVER"}
SELL_WORDS = {"SELL", "SLD", "S", "STO", "STC", "SELL_TO_OPEN", "SELL_TO_CLOSE", "SELL TO OPEN",
              "SELL TO CLOSE", "SOLD", "SHORT", "SELL_SHORT", "SS"}


@dataclass
class Fill:
    time: datetime
    symbol: str
    sign: int
    qty: float
    price: float
    fees: float
    net: float | None
    und: float | None = None


def load_fills(path: str, tz: str = "ET") -> list[Fill]:
    """Read fills from a normalized CSV or straight from a broker export (see import_fills.py)."""
    out = []
    rows = None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import import_fills  # noqa: WPS433
        kind, conv = import_fills.convert(path, tz)
        if kind != "generic":
            print(f"fills: detected {kind} export, {len(conv)} fills", file=sys.stderr)
            rows = conv
    except (ImportError, StopIteration, KeyError, ValueError) as e:
        print(f"fills: broker auto-detect skipped ({e.__class__.__name__}); reading as normalized CSV",
              file=sys.stderr)
    if rows is None:
        text = Path(path).read_text(encoding="utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))
        # bare times without a zone take --fills-tz
        for r in rows:
            for k in list(r):
                if k and k.strip().lower() in ("time", "timestamp", "datetime", "date/time") and r[k] \
                        and not re.search(r"(Z|[+-]\d{2}:?\d{2}|[A-Z]{2,3})$", r[k].strip()):
                    r[k] = f"{r[k].strip()} {tz}"
    for r in rows:
        low = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        g = lambda *ks: next((low[k] for k in ks if low.get(k)), "")  # noqa: E731
        t = g("time", "timestamp", "datetime", "date/time", "filled at", "fill time", "filled time", "exec time",
              "execution time", "executed", "date")
        sym = g("symbol", "contract", "instrument", "ticker", "description")
        side = g("side", "action", "b/s", "buy/sell", "trans code", "type").upper()
        qty = g("qty", "quantity", "filled qty", "filled", "size", "contracts", "shares")
        px = g("price", "fill price", "avg price", "avgprice", "avg fill price", "execution price", "tradeprice")
        if not (t and sym and qty and px):
            continue
        q = _num(qty)
        if side in BUY_WORDS or side.startswith("BUY") or side.startswith("BOUGHT"):
            sign = 1
        elif side in SELL_WORDS or side.startswith("SELL") or side.startswith("SOLD"):
            sign = -1
        elif q != 0:
            sign = 1 if q > 0 else -1
        else:
            continue
        fees = _num(g("fees", "fee", "commission", "commissions", "comm") or 0)
        net = g("net", "net amount", "amount", "proceeds")
        out.append(Fill(parse_time(t), sym, sign, abs(q), _num(px), fees, _num(net) if net else None))
    out.sort(key=lambda f: f.time)
    return out


@dataclass
class Position:
    inst: Instrument
    fills: list[Fill] = field(default_factory=list)
    status: str = "closed"

    @property
    def side(self) -> int:  # +1 long the instrument, -1 short it
        return self.fills[0].sign

    @property
    def direction(self) -> str:
        bull = self.side > 0
        if self.inst.asset == "option" and self.inst.cp == "P":
            bull = not bull
        return "BULL" if bull else "BEAR"

    def entries(self):
        return [f for f in self.fills if f.sign == self.side]

    def exits(self):
        return [f for f in self.fills if f.sign != self.side]

    def qty(self):
        return sum(f.qty for f in self.entries())

    def avg_entry(self):
        e = self.entries()
        return sum(f.qty * f.price for f in e) / sum(f.qty for f in e)

    def avg_exit(self):
        x = self.exits()
        return sum(f.qty * f.price for f in x) / sum(f.qty for f in x) if x else None

    def net(self, f: Fill) -> float:
        if f.net is not None:
            return f.net
        return -f.sign * f.qty * f.price * self.inst.multiplier - f.fees

    def pnl(self):
        return sum(self.net(f) for f in self.fills)


def build_positions(fills: list[Fill], asset_hint, mult) -> list[Position]:
    by_sym: dict[str, list[Fill]] = {}
    for f in fills:
        by_sym.setdefault(f.symbol, []).append(f)
    out = []
    for sym, fs in by_sym.items():
        inst = parse_instrument(sym, asset_hint, mult)
        pos, run = None, 0.0
        for f in fs:
            if pos is None:
                pos, run = Position(inst), 0.0
            pos.fills.append(f)
            run += f.sign * f.qty
            if abs(run) < 1e-9:
                out.append(pos)
                pos = None
        if pos is not None:
            pos.status = "open"
            out.append(pos)
    out.sort(key=lambda p: p.fills[0].time)
    return out


# ----------------------------------------------------------------------------- Strat grammar

def structure(cur: Bar, prior: Bar) -> str:
    up, dn = cur.high > prior.high, cur.low < prior.low  # equal is not a break
    return "3" if up and dn else "2u" if up else "2d" if dn else "1"


def failed(cur: Bar, prior: Bar, st: str) -> bool:  # Reclaim method (Suite default)
    return st in ("2u", "2d") and prior.low <= cur.close <= prior.high


def above_open(b: Bar) -> bool:
    return b.close > b.open  # flat buckets down


def token(cur: Bar, prior: Bar | None) -> str:
    """Chart-convention notation: 1u/1d, 2u/2d, F2u/F2d, 3u/3d."""
    if prior is None:
        return "?"
    st = structure(cur, prior)
    if st in ("2u", "2d"):
        return ("F" if failed(cur, prior, st) else "") + st
    return st + ("u" if above_open(cur) else "d")


def combo_token(cur: Bar, prior: Bar | None) -> str:
    """Combo-slot notation: 1, 2u, 2d, F2u, F2d, 3."""
    if prior is None:
        return "?"
    st = structure(cur, prior)
    if st in ("2u", "2d") and failed(cur, prior, st):
        return "F" + st
    return st


# ----------------------------------------------------------------------------- sessions & timeframes

@dataclass
class SessionSpec:
    open_t: time
    close_t: time
    overnight: bool  # session starts the prior calendar day (futures)

    def start_of(self, t: datetime) -> datetime:
        e = t.astimezone(ET)
        d = e.date()
        if self.overnight:
            if e.time() < self.open_t:
                d -= timedelta(days=1)
        return datetime.combine(d, self.open_t, ET)

    def end_of(self, start: datetime) -> datetime:
        d = start.date() + (timedelta(days=1) if self.overnight else timedelta())
        return datetime.combine(d, self.close_t, ET)

    def contains(self, t: datetime) -> bool:
        s = self.start_of(t)
        return s <= t.astimezone(ET) < self.end_of(s)


TF_MIN = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60, "1h": 60, "2h": 120, "4h": 240}


def aggregate(bars: list[Bar], tf: str, sess: SessionSpec, upto: datetime | None = None) -> list[Bar]:
    """Clock-aligned TF bars from the session open, built only from base bars that closed by `upto`."""
    out: list[Bar] = []
    cur_key = None
    for b in bars:
        if upto is not None and b.end > upto:
            break
        if not sess.contains(b.start):
            continue
        s0 = sess.start_of(b.start)
        if tf == "D":
            key, kstart = s0, s0
        else:
            m = TF_MIN[tf]
            n = int((b.start - s0).total_seconds() // (m * 60))
            kstart = s0 + timedelta(minutes=m * n)
            key = kstart
        if key != cur_key:
            nb = Bar(kstart, b.open, b.high, b.low, b.close, b.end)
            out.append(nb)
            cur_key = key
        else:
            out[-1].merge(b)
    return out


def tf_end(b: Bar, tf: str, sess: SessionSpec) -> datetime:
    if tf == "D":
        return sess.end_of(b.start)
    return min(b.start + timedelta(minutes=TF_MIN[tf]), sess.end_of(sess.start_of(b.start)))


def tf_state(bars, tf, sess, at: datetime, daily_hist: list[Bar], last_is_cc: bool = False):
    """C2, C1 and forming CC for `tf`, using only data closed by `at`.

    At a TF boundary the last built bar is complete; a fill there sees a new CC with no
    closed base bar yet (cc=None) unless `last_is_cc` (used while walking bars).
    """
    agg = aggregate(bars, tf, sess, upto=at)
    if tf == "D":
        prior_days = [d for d in daily_hist if d.start.astimezone(ET).date() < sess.start_of(at).date()
                      + (timedelta(days=1) if sess.overnight else timedelta())]
        today = [b for b in agg if b.start == sess.start_of(at)]
        hist = [b for b in agg if b.start < sess.start_of(at)]
        seq = (prior_days if prior_days else hist)[-2:] + today
    else:
        seq = agg
    if not seq:
        return None
    last = seq[-1]
    forming = last_is_cc or tf_end(last, tf, sess) > at
    if not forming:
        # the forming TF bar has no closed base bar yet
        return dict(c2=seq[-2] if len(seq) >= 2 else None, c1=last, cc=None)
    return dict(c2=seq[-3] if len(seq) >= 3 else None, c1=seq[-2] if len(seq) >= 2 else None, cc=last)


def describe_state(st) -> dict:
    if st is None:
        return {"cc": "-", "combo": "-", "sign": None, "c1_high": None, "c1_low": None}
    c2, c1, cc = st["c2"], st["c1"], st["cc"]
    c1tok = combo_token(c1, c2) if c1 and c2 else "?"
    if cc is None:
        return {"cc": "new bar", "combo": f"{c1tok}-(new)", "sign": None,
                "c1_high": c1.high if c1 else None, "c1_low": c1.low if c1 else None}
    cct = token(cc, c1) if c1 else "?"
    return {"cc": cct, "combo": f"{c1tok}-{combo_token(cc, c1) if c1 else '?'}",
            "sign": above_open(cc), "c1_high": c1.high if c1 else None, "c1_low": c1.low if c1 else None,
            "cc_open": cc.open, "cc_last": cc.close}


def continuity(signs: list[bool | None]) -> str:
    s = [x for x in signs if x is not None]
    if not s:
        return "n/a"
    return "FTFC Up" if all(s) else "FTFC Down" if not any(s) else "Conflict"


# ----------------------------------------------------------------------------- triggers

def family(c2tok: str, c1tok: str, d: str) -> str:
    opp = "2d" if d == "2u" else "2u"
    c1b = c1tok.lstrip("F")
    if c1b == "1":
        c2b = c2tok.lstrip("F")
        if c2b == d:
            return "Inside Continuation"
        return "Inside Reversal"
    if c1b == "3":
        return "3-2 Expansion"
    if c1b == opp or (c1tok.startswith("F") and c1b == d):
        return "2-2 Reversal"
    return "2-2 Continuation"


def session_triggers(bars, tf, sess, daily_hist, session_start) -> list[dict]:
    """Every first cross of C1 high (2u) or C1 low (2d) per TF bar during the session."""
    events = []
    sess_bars = [b for b in bars if sess.start_of(b.start) == session_start and sess.contains(b.start)]
    fired: set = set()
    for b in sess_bars:
        st = tf_state(bars, tf, sess, b.end, daily_hist, last_is_cc=True)
        if not st or not st["c1"] or st["cc"] is None:
            continue
        c2, c1, cc = st["c2"], st["c1"], st["cc"]
        c1tok = combo_token(c1, c2) if c2 else "?"
        c2tok = "?"
        if c2 is not None:
            # C2 token needs C3; approximate with C2's own sign when unknown
            c2tok = "2u" if above_open(c2) else "2d"
            st3 = None
            agg = aggregate(bars, tf, sess, upto=b.end) if tf != "D" else None
            if agg:
                idx = [i for i, x in enumerate(agg) if x.start == c2.start]
                if idx and idx[0] > 0:
                    st3 = agg[idx[0] - 1]
            if st3 is not None:
                c2tok = combo_token(c2, st3)
        for d, lvl, cond in (("2u", c1.high, cc.high > c1.high), ("2d", c1.low, cc.low < c1.low)):
            k = (cc.start, d)
            if cond and k not in fired:
                fired.add(k)
                bull = d == "2u"
                stop = c1.low if bull else c1.high
                mag = None
                if c2 is not None:
                    m = c2.high if bull else c2.low
                    if (m > lvl) if bull else (m < lvl):
                        mag = m
                combo = (f"{c2tok}-1-{d}" if c1tok == "1" else f"{c1tok}-{d}")
                # opened through the level: there was never a fill at the trigger price
                gap = b.start == cc.start and ((b.open > lvl) if bull else (b.open < lvl))
                events.append(dict(tf=tf, time=b.start, bar_start=cc.start, dir="BULL" if bull else "BEAR",
                                   combo=combo, family=family(c2tok, c1tok, d), trigger=lvl, stop_c1=stop,
                                   magnitude=mag, gap=gap))
    return events


def outcome(ev, bars, sess_end, levels_beyond):
    """Walk forward from the trigger: stop first or target first, MFE in R."""
    bull = ev["dir"] == "BULL"
    risk = abs(ev["trigger"] - ev["stop_c1"]) or 1e-9
    target = ev["magnitude"]
    if target is None and levels_beyond:
        target = levels_beyond[0]
    hit_t = stop_t = None
    mfe = 0.0
    for b in bars:
        if b.start < ev["time"] or b.start >= sess_end:
            continue
        fav = (b.high - ev["trigger"]) if bull else (ev["trigger"] - b.low)
        adverse_hit = (b.low <= ev["stop_c1"]) if bull else (b.high >= ev["stop_c1"])
        if b.start > ev["time"] and adverse_hit and stop_t is None and hit_t is None:
            stop_t = b.start
        if stop_t is None:
            mfe = max(mfe, fav)
            if target is not None and hit_t is None and ((b.high >= target) if bull else (b.low <= target)):
                hit_t = b.start
    ev.update(target=target, risk_pts=risk, mfe_r=mfe / risk, target_hit=hit_t, stopped=stop_t,
              result=("target first" if hit_t and (not stop_t or hit_t <= stop_t)
                      else "stopped first" if stop_t else "open at close"))
    return ev


# ----------------------------------------------------------------------------- pricing

def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(S, K, T, vol, cp, r=0.04):
    intrinsic = max(0.0, S - K) if cp == "C" else max(0.0, K - S)
    if T <= 0 or vol <= 0:
        return intrinsic
    d1 = (math.log(S / K) + (r + 0.5 * vol * vol) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    if cp == "C":
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def bs_delta(S, K, T, vol, cp, r=0.04):
    if T <= 0 or vol <= 0:
        return (1.0 if S > K else 0.0) if cp == "C" else (-1.0 if S < K else 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * vol * vol) * T) / (vol * math.sqrt(T))
    return _ncdf(d1) if cp == "C" else _ncdf(d1) - 1


def implied_vol(price, S, K, T, cp):
    lo, hi = 1e-4, 8.0
    if price <= bs_price(S, K, T, lo, cp):
        return lo
    for _ in range(100):
        mid = (lo + hi) / 2
        if bs_price(S, K, T, mid, cp) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


class Pricer:
    """Instrument price at a moment: real contract bars when available, else a labeled estimate."""

    def __init__(self, inst: Instrument, und_bars, contract_bars, pos: Position | None, sess: SessionSpec):
        self.inst, self.und, self.cbars, self.sess = inst, und_bars, contract_bars, sess
        self.vol = None
        self.source = "underlying bars"
        if inst.asset == "option":
            if contract_bars:
                self.source = "contract bars"
            else:
                self.source = "ESTIMATE (Black-Scholes, IV implied from your fills)"
                vols = []
                for f in (pos.entries() if pos else []):
                    S = und_at_fill(und_bars, f.time)
                    if S:
                        vols.append(implied_vol(f.price, S, inst.strike, self.T(f.time), inst.cp))
                self.vol = sum(vols) / len(vols) if vols else 0.25

    def T(self, t):
        exp_close = datetime.combine(self.inst.expiration, time(16, 0), ET)
        return max((exp_close - t).total_seconds(), 0) / (365 * 24 * 3600)

    def at(self, t: datetime, und_price: float | None = None) -> float | None:
        if self.inst.asset != "option":
            return und_price if und_price is not None else und_at(self.und, t)
        if self.cbars and und_price is None:
            return und_at(self.cbars, t)
        S = und_price if und_price is not None else und_at(self.und, t)
        if S is None:
            return None
        if self.cbars and und_price is not None:
            # level-based exit with real bars: use the contract bar covering that moment
            return und_at(self.cbars, t)
        return bs_price(S, self.inst.strike, self.T(t), self.vol, self.inst.cp)

    def delta(self, t):
        if self.inst.asset != "option":
            return 1.0
        S = und_at(self.und, t)
        vol = self.vol
        if vol is None:  # real bars: back IV out of the contract mark
            c = und_at(self.cbars, t)
            vol = implied_vol(c, S, self.inst.strike, self.T(t), self.inst.cp) if c and S else 0.25
        return bs_delta(S, self.inst.strike, self.T(t), vol, self.inst.cp)

    def bar_ranges(self, t0, t1):
        """(bar end, low, high) of the instrument for each bar overlapping [t0, t1]."""
        src = self.cbars if (self.inst.asset == "option" and self.cbars) else self.und
        for b in src:
            if b.end <= t0 or b.start >= t1:
                continue
            if src is self.und and self.inst.asset == "option":
                v = sorted(bs_price(s, self.inst.strike, self.T(b.end), self.vol, self.inst.cp) for s in (b.low, b.high))
            else:
                v = [b.low, b.high]
            yield b, v[0], v[1]


def und_at(bars, t: datetime):
    """Close of the last bar that ended at or before t (falls back to the open of the bar containing t)."""
    best = None
    for b in bars:
        if b.end <= t:
            best = b.close
        elif b.start <= t < b.end and best is None:
            best = b.open
        elif b.start > t:
            break
    return best


def und_at_fill(bars, t: datetime):
    """Underlying at a fill: interpolate open->close inside the bar that contains t.

    Used only to display the underlying and calibrate option IV; Strat states never see it.
    """
    for b in bars:
        if b.start <= t < b.end:
            frac = (t - b.start).total_seconds() / max((b.end - b.start).total_seconds(), 1)
            return round(b.open + (b.close - b.open) * frac, 2)
    return und_at(bars, t)


def trail_exit(bars, sess, start: datetime, until: datetime, floor: float, bull: bool, trail_tf: str):
    """Runner exit: stop starts at `floor` (breakeven) and ratchets to each completed `trail_tf`
    bar's low (bull) / high (bear) once that bar closes. Returns (bar, level) or (None, None)."""
    stop = floor
    agg = aggregate(bars, trail_tf, sess)
    for b in bars:
        if b.end <= start or b.start >= until:
            continue
        done = [x for x in agg if x.start >= start - timedelta(minutes=TF_MIN.get(trail_tf, 60))
                and tf_end(x, trail_tf, sess) <= b.start]
        for x in done:
            stop = max(stop, x.low) if bull else min(stop, x.high)
        if (b.low <= stop) if bull else (b.high >= stop):
            return b, stop
    return None, None


def first_touch(bars, after, level, up: bool, until=None):
    for b in bars:
        if b.start < after - (b.end - b.start) or (until and b.start >= until):
            continue
        if b.end <= after:
            continue
        if (b.high >= level) if up else (b.low <= level):
            return b
    return None


# ----------------------------------------------------------------------------- report

def money(x):
    return "-" if x is None else (f"+${x:,.2f}" if x >= 0 else f"-${-x:,.2f}")


def run(args):
    clock = Clock(args.display_tz)
    fills = load_fills(args.fills, args.fills_tz)
    if not fills:
        sys.exit("No fills parsed. Expected columns: time, symbol, side, qty, price (fees, net optional).")
    positions = build_positions(fills, args.asset, args.multiplier)
    if args.symbol:
        positions = [p for p in positions if args.symbol.upper() in (p.inst.symbol.upper(), p.inst.underlying)]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    bars_path = args.bars
    if not bars_path and args.fetch == "yfinance":
        und = args.yf_symbol or positions[0].inst.underlying
        bars_path = str(fetch_yfinance(und, fills[0].time.astimezone(ET).date(), args.interval,
                                       out / f"{und.replace('=', '_')}_{args.interval}.csv"))
    if not bars_path:
        sys.exit("Need --bars FILE (or --fetch yfinance).")
    bars = load_bars(bars_path)
    daily = load_bars(args.daily) if args.daily else []
    cbars = load_bars(args.contract_bars) if args.contract_bars else []

    fut = any(p.inst.asset == "future" for p in positions) or args.session == "futures"
    if args.session == "futures" or (args.session == "auto" and fut):
        sess = SessionSpec(time(18, 0), time(17, 0), True)
    else:
        o, c = (args.session_hours or "09:30-16:00").split("-")
        sess = SessionSpec(time.fromisoformat(o), time.fromisoformat(c), False)
    # full context: the prior session's intraday bars (C1/C2 for the day's first bars) and prior daily bars
    if not args.no_auto_context:
        bars, daily = ensure_context(bars, daily, positions, sess, args, out)
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]            # vote on continuity and flags
    ctx_tfs = [t.strip() for t in args.context_tfs.split(",") if t.strip() and t.strip() not in tfs]
    show_tfs = tfs + ctx_tfs                                                  # shown, context only

    report = {"positions": [], "display_tz": args.display_tz}
    md = []
    day_pnl_path = []

    for pi, pos in enumerate(positions, 1):
        inst = pos.inst
        s0 = sess.start_of(pos.fills[0].time)
        s_end = sess.end_of(s0)
        sbars = [b for b in bars if sess.start_of(b.start) == s0 and sess.contains(b.start)]
        if not sbars:
            md.append(f"## {inst.label()}: no underlying bars for this session, skipped\n")
            continue
        for f in pos.fills:
            f.und = und_at_fill(bars, f.time)
        if not any(sess.start_of(b.start) < s0 and sess.contains(b.start) for b in bars):
            md.append("_No bars from the prior session: the first bars of each timeframe show `?` because there is "
                      "no prior bar to compare them with. Add the previous session's bars to resolve them._\n")
        pricer = Pricer(inst, bars, [c for c in cbars], pos, sess)
        day_pnl_path.append((pos, pricer))
        bull = pos.direction == "BULL"
        last_exit = pos.exits()[-1].time if pos.exits() else sbars[-1].end
        mark_t = parse_time(args.mark) if args.mark else min(sbars[-1].end, s_end)

        # reference levels
        prior = None
        if daily:
            pd = [d for d in daily if d.start.astimezone(ET).date() < (s0 + (timedelta(days=1) if sess.overnight else timedelta())).date()]
            prior = pd[-1] if pd else None
        else:
            prev = [b for b in bars if sess.start_of(b.start) < s0 and sess.contains(b.start)]
            if prev:
                ps = sess.start_of(prev[-1].start)
                pb = [b for b in prev if sess.start_of(b.start) == ps]
                prior = Bar(ps, pb[0].open, max(b.high for b in pb), min(b.low for b in pb), pb[-1].close)
        or_bars = [b for b in sbars if b.start < s0 + timedelta(minutes=args.or_minutes)]
        levels = {"day open": sbars[0].open,
                  f"opening range high ({args.or_minutes}m)": max(b.high for b in or_bars),
                  f"opening range low ({args.or_minutes}m)": min(b.low for b in or_bars)}
        if prior:
            levels.update({"prior close (gap fill)": prior.close, "prior day high": prior.high,
                           "prior day low": prior.low})
        hod = max(sbars, key=lambda b: b.high)
        lod = min(sbars, key=lambda b: b.low)

        # multi-TF state at each fill
        fill_states = []
        for f in pos.fills:
            states = {tf: describe_state(tf_state(bars, tf, sess, f.time, daily)) for tf in show_tfs}
            cont = continuity([states[tf]["sign"] for tf in tfs])
            fill_states.append((f, states, cont))

        # flags
        flags = []
        entries = pos.entries()
        if len(entries) > 1:
            flags.append("SCALED_IN")
            first = entries[0].price
            if any((e.price < first) if pos.side > 0 else (e.price > first) for e in entries[1:]):
                flags.append("AVERAGED_DOWN")
        if len(pos.exits()) > 1:
            flags.append("SCALED_OUT")
        for f, states, cont in fill_states:
            if f.sign != pos.side:
                continue
            signs = [states[tf]["sign"] for tf in tfs if states[tf]["sign"] is not None]
            against = sum(1 for s in signs if s != bull)
            if cont == ("FTFC Down" if bull else "FTFC Up"):
                flags.append("AGAINST_FTFC")
            if against > len(signs) / 2:
                flags.append("AGAINST_CONTINUITY")
            if args.caution_until and f.time.astimezone(ET).time() < time.fromisoformat(args.caution_until) \
                    and not sess.overnight:
                flags.append("EARLY_SESSION")
        flags = list(dict.fromkeys(flags))

        # triggers on every TF
        all_events = []
        for tf in show_tfs:
            for ev in session_triggers(bars, tf, sess, daily, s0):
                lv = sorted([v for v in list(levels.values()) + [hod.high if ev["dir"] == "BEAR" else lod.low]
                             if ((v > ev["trigger"]) if ev["dir"] == "BULL" else (v < ev["trigger"]))],
                            key=lambda v: abs(v - ev["trigger"]))
                all_events.append(outcome(ev, sbars, s_end, lv))
        all_events.sort(key=lambda e: (e["time"], show_tfs.index(e["tf"])))

        # MAE / MFE while held
        first_t = entries[0].time
        unit = inst.multiplier

        def open_pnl(price_now, upto):
            """P/L of the position (realized + open) if marked at price_now with fills through `upto`."""
            pnl, q = 0.0, 0.0
            for f in pos.fills:
                if f.time <= upto:
                    pnl += pos.net(f)
                    q += f.sign * f.qty
            return pnl + q * price_now * unit

        # open P/L at every bar while held, with the size actually held then
        mae = mfe = None
        mae_t = None
        for b, lo, hi in pricer.bar_ranges(first_t, last_exit):
            done = [f for f in pos.fills if f.time < b.end]
            held = sum(f.sign * f.qty for f in done)
            if not done or abs(held) < 1e-9:
                continue
            cash = sum(pos.net(f) for f in done)
            vals = [cash + held * px * unit for px in (lo, hi)]
            if mae is None or min(vals) < mae:
                mae, mae_t = min(vals), b.start
            mfe = max(vals) if mfe is None else max(mfe, max(vals))

        # alternatives
        q = pos.qty()
        alts = []
        actual = pos.pnl()
        alts.append(("Actual", actual, "your fills"))
        cost_all = sum(pos.net(f) for f in entries)

        def exit_val(qty, price):
            return pos.side * qty * price * unit if price is not None else None

        mark_px = pricer.at(mark_t)
        if mark_px is not None:
            alts.append((f"Hold all {q:g} to {clock.fmt(mark_t)}", cost_all + exit_val(q, mark_px), pricer.source))
            run_q = max(1.0, round(q * args.runner_fraction)) if q > 1 else 0
            if run_q and pos.exits():
                ax = pos.avg_exit()
                alts.append((f"Your exits on {q - run_q:g}, {run_q:g} runner to {clock.fmt(mark_t)}",
                             cost_all + exit_val(q - run_q, ax) + exit_val(run_q, mark_px), pricer.source))
                half = math.floor(q / 2)
                if half and half != run_q:
                    alts.append((f"Your exits on {q - half:g}, {half:g} runners to {clock.fmt(mark_t)}",
                                 cost_all + exit_val(q - half, ax) + exit_val(half, mark_px), pricer.source))
        # clean Strat entry: the first --entry-tf trigger in the trade's direction
        cand_ev = [e for e in all_events if e["tf"] == args.entry_tf and e["dir"] == pos.direction and not e["gap"]]
        if args.clean_entry:
            ct = parse_time(args.clean_entry)
            cand_ev = [e for e in cand_ev if e["time"] >= ct - timedelta(minutes=1)]
        else:
            tol = timedelta(minutes=TF_MIN.get(args.entry_tf, 30))
            cand_ev = [e for e in cand_ev if e["time"] >= first_t - tol]
        clean_ev = cand_ev[0] if cand_ev else None
        clean_tgt = None
        if clean_ev:
            risk_pts = abs(clean_ev["trigger"] - clean_ev["stop_c1"])
            pool = ([clean_ev["magnitude"]] if clean_ev["magnitude"] else []) + list(levels.values())
            pool = sorted({v for v in pool if (v - clean_ev["trigger"]) * (1 if bull else -1)
                           >= args.min_target_r * risk_pts}, key=lambda v: abs(v - clean_ev["trigger"]))
            clean_tgt = args.t1 if args.t1 is not None else (pool[0] if pool else None)
        # T1: the clean plan's first target, else the nearest reference level beyond the last entry
        last_entry = entries[-1]
        ref = last_entry.und or und_at(bars, last_entry.time)
        cand = sorted([v for v in levels.values() if ((v > ref) if bull else (v < ref))],
                      key=lambda v: abs(v - ref))
        t1 = clean_tgt if clean_tgt is not None else (args.t1 if args.t1 is not None else (cand[0] if cand else None))
        t1_bar = first_touch(sbars, last_entry.time, t1, bull) if t1 is not None else None
        if t1_bar is not None:
            px_t1 = pricer.at(t1_bar.end, und_price=t1)
            if px_t1 is not None:
                alts.append((f"All {q:g} out at T1 {t1:.2f} ({clock.fmt(t1_bar.start)})",
                             cost_all + exit_val(q, px_t1), pricer.source))
                if mark_px is not None and q >= 2:
                    h = math.floor(q / 2)
                    # runner: breakeven stop on the underlying at the avg-entry underlying level
                    be_level = sum(e.qty * (e.und or 0) for e in entries) / q
                    be_bar, lvl = trail_exit(sbars, sess, t1_bar.end, mark_t, be_level, bull, args.trail_tf)
                    r_px = pricer.at(be_bar.end, und_price=lvl) if be_bar else mark_px
                    note = (f"trail stop {lvl:.2f} hit {clock.fmt(be_bar.start)}" if be_bar
                            else f"held to {clock.fmt(mark_t)}")
                    alts.append((f"{q - h:g} at T1, {h:g} runner ({note})",
                                 cost_all + exit_val(q - h, px_t1) + exit_val(h, r_px), pricer.source))

        # clean Strat version
        clean = None
        if clean_ev:
            ev = clean_ev
            et = ev["time"]
            step = sbars[0].end - sbars[0].start
            entry_px = pricer.at(et + step, und_price=ev["trigger"])  # the trigger bar's close for real bars
            stop_lvl = ev["stop_c1"]
            if inst.asset == "option":
                # what the contract would be worth with the underlying at the stop, at entry time
                iv = pricer.vol or implied_vol(entry_px, ev["trigger"], inst.strike, pricer.T(et + step), inst.cp)
                stop_px = bs_price(stop_lvl, inst.strike, pricer.T(et + step), iv, inst.cp)
            else:
                stop_px = stop_lvl
            risk = pos.side * q * (entry_px - stop_px) * unit if entry_px is not None and stop_px is not None else None
            tgt = clean_tgt
            stop_bar = first_touch(sbars, et + (sbars[0].end - sbars[0].start), stop_lvl, not bull)
            tgt_bar = first_touch(sbars, et, tgt, bull) if tgt else None
            h = math.floor(q / 2)
            if stop_bar and (not tgt_bar or stop_bar.start < tgt_bar.start):
                pnl = pos.side * q * (pricer.at(stop_bar.end, und_price=stop_lvl) - entry_px) * unit
                path = f"stopped at {stop_lvl:.2f} ({clock.fmt(stop_bar.start)})"
            elif tgt_bar:
                p1 = pricer.at(tgt_bar.end, und_price=tgt)
                be_bar, lvl = trail_exit(sbars, sess, tgt_bar.end, mark_t, ev["trigger"], bull, args.trail_tf)
                p2 = pricer.at(be_bar.end, und_price=lvl) if be_bar else mark_px
                pnl = pos.side * ((q - h) * (p1 - entry_px) + h * (p2 - entry_px)) * unit
                path = (f"{q - h:g} at target {tgt:.2f} ({clock.fmt(tgt_bar.start)})"
                        + ("" if not h else f", {h:g} runner " + (f"trail stop {lvl:.2f} hit {clock.fmt(be_bar.start)}"
                                                                  if be_bar else f"to {clock.fmt(mark_t)}")))
            else:
                pnl = pos.side * q * ((mark_px or entry_px) - entry_px) * unit
                path = f"no target or stop by {clock.fmt(mark_t)}"
            clean = dict(event=ev, entry_px=entry_px, stop_px=stop_px, risk=risk, pnl=pnl, path=path)
            alts.append((f"Clean Strat: {q:g} on {ev['tf']} {ev['combo']} trigger {ev['trigger']:.2f} "
                         f"({clock.fmt(et)}), stop {stop_lvl:.2f}; {path}", pnl,
                         pricer.source + (f"; risk to stop about {money(-abs(risk))}" if risk is not None else "")))

        # delta at exit
        dlt = None
        if pos.exits():
            dx = pricer.delta(pos.exits()[0].time)
            und_px = und_at(bars, pos.exits()[0].time)
            dlt = dict(per_unit=dx, position_delta=dx * q * unit * pos.side,
                       notional=abs(dx * q * unit) * (und_px or 0))

        # ---------- markdown
        md.append(f"## {pi}. {inst.label()} {pos.direction} ({inst.asset}, x{unit:g}) : {money(actual)}"
                  + (" (OPEN, marked)" if pos.status == "open" else ""))
        md.append("")
        md.append("### Fills\n")
        md.append(f"| Time | Side | Qty | Price | Net | {inst.underlying} |")
        md.append("|---|---|---|---|---|---|")
        for f in pos.fills:
            md.append(f"| {clock.fmt(f.time)} | {'BUY' if f.sign > 0 else 'SELL'} | {f.qty:g} | {f.price:g} | "
                      f"{money(pos.net(f))} | {f.und if f.und is not None else '-'} |")
        md.append("")
        md.append(f"Avg entry {pos.avg_entry():.4g}, avg exit {pos.avg_exit() or 0:.4g}. "
                  f"While held: worst open P/L {money(mae)} ({clock.fmt(mae_t)}), best {money(mfe)} "
                  f"({pricer.source}).")
        md.append("")
        md.append(f"**Flags:** {', '.join(flags) if flags else 'none'}\n")
        md.append("### TheStrat state at each fill\n")
        md.append("Forming bar (CC) vs prior bar (C1), built only from bars closed by the fill. "
                  "Sign = forming bar above (+) or at/below (-) its open.\n")
        md.append("| Fill | " + " | ".join(tfs + [f"{t} (context)" for t in ctx_tfs]) + " | Continuity |")
        md.append("|---|" + "---|" * len(show_tfs) + "---|")
        for f, states, cont in fill_states:
            cells = []
            for tf in show_tfs:
                s = states[tf]
                sg = "" if s["sign"] is None else (" +" if s["sign"] else " -")
                cells.append(f"{s['combo']}{sg}")
            md.append(f"| {clock.fmt(f.time)} {'BUY' if f.sign > 0 else 'SELL'} {f.qty:g} | " + " | ".join(cells)
                      + f" | {cont} |")
        md.append("")
        md.append("### Session triggers\n")
        md.append("Every first break of the prior bar's high (2u) or low (2d), per timeframe. Stop = C1's opposite "
                  "side (Suite 'C1' stop mode). Target = magnitude (C2 extreme) if it lies beyond the trigger, else "
                  "the nearest reference level.\n")
        md.append("| Time | TF | Dir | Combo | Family | Trigger | Stop | Target | Result | MFE (R) |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for e in all_events:
            if e["tf"] != "D" and args.triggers_window and abs((e["time"] - first_t).total_seconds()) > args.triggers_window * 3600:
                continue
            mark = " **(with trade)**" if e["dir"] == pos.direction else ""
            md.append(f"| {clock.fmt(e['time'])} | {e['tf']} | {e['dir']}{mark} | {e['combo']} | {e['family']} | "
                      f"{e['trigger']:.2f} | {e['stop_c1']:.2f} | "
                      f"{'-' if e['target'] is None else format(e['target'], '.2f')} | "
                      f"{'gapped through, no fill at the trigger' if e['gap'] else e['result']} | {e['mfe_r']:.1f} |")
        md.append("")
        md.append("### Reference levels\n")
        for k, v in levels.items():
            md.append(f"- {k}: {v:.2f}")
        md.append(f"- HOD {hod.high:.2f} ({clock.fmt(hod.start)}), LOD {lod.low:.2f} ({clock.fmt(lod.start)})")
        md.append("")
        md.append("### Alternatives\n")
        r_unit = abs(clean["risk"]) if clean and clean.get("risk") else None
        md.append("| Plan | P/L | R | Priced from |")
        md.append("|---|---|---|---|")
        for name, v, src in alts:
            md.append(f"| {name} | {money(v)} | {'-' if not r_unit else f'{v / r_unit:+.1f}R'} | {src} |")
        if r_unit:
            md.append(f"\n1R = {money(r_unit)}, the clean plan's dollar risk from trigger to C1 stop at the same size. "
                      f"Runners trail under each completed {args.trail_tf} bar's "
                      f"{'low' if bull else 'high'}, starting from breakeven.")
        md.append("")
        if dlt:
            if inst.asset == "option":
                md.append(f"Delta at first exit: {dlt['per_unit']:.2f} per contract, position ~{dlt['position_delta']:.0f} "
                          f"{inst.underlying} share-equivalents (~${dlt['notional']:,.0f} notional). Use this before "
                          "comparing to shares or leveraged ETFs.\n")
            else:
                md.append(f"Exposure at first exit: ~${dlt['notional']:,.0f} notional "
                          f"({q:g} x {unit:g} x {inst.underlying}).\n")
        report["positions"].append(dict(
            symbol=inst.symbol, label=inst.label(), asset=inst.asset, direction=pos.direction,
            status=pos.status, pnl=actual, qty=q, avg_entry=pos.avg_entry(), avg_exit=pos.avg_exit(),
            flags=flags, mae=mae, mfe=mfe, pricing_source=pricer.source, implied_vol=pricer.vol,
            fills=[dict(time=f.time.isoformat(), side="BUY" if f.sign > 0 else "SELL", qty=f.qty,
                        price=f.price, net=pos.net(f), underlying=f.und,
                        states=st, continuity=c) for (f, st, c) in fill_states],
            triggers=[{**e, "time": e["time"].isoformat(), "bar_start": e["bar_start"].isoformat(),
                       "target_hit": e["target_hit"].isoformat() if e["target_hit"] else None,
                       "stopped": e["stopped"].isoformat() if e["stopped"] else None} for e in all_events],
            levels=levels, hod=hod.high, lod=lod.low, t1=t1,
            alternatives=[dict(plan=a, pnl=v, source=s) for a, v, s in alts],
            delta=dlt, clean=None if not clean else {**{k: (v if k != "event" else v["combo"]) for k, v in clean.items()},
                                                      "tf": clean["event"]["tf"], "time": clean["event"]["time"].isoformat(),
                                                      "trigger": clean["event"]["trigger"],
                                                      "stop_c1": clean["event"]["stop_c1"]},
            cost=sum(abs(pos.net(f)) for f in entries), tfs=tfs,
        ))
        if args.chart:
            cpath = out / f"chart_{pi}_{re.sub(r'[^A-Za-z0-9]+', '_', inst.label())}.png"
            report["positions"][-1]["chart"] = cpath.name
            try:
                chart(cpath, sbars, pos, levels,
                      clean, clock, sess, args.chart_tf, bars, daily, args.candles)
            except ImportError:
                md.append("_Chart skipped: matplotlib not installed._\n")
            else:
                mpath = out / f"timeframes_{pi}_{re.sub(r'[^A-Za-z0-9]+', '_', inst.label())}.png"
                cost = sum(abs(pos.net(f)) for f in entries)
                extra = (f"{pos.direction}  ·  net {money(actual)}"
                         + (f" ({actual / cost:+.0%} on {money(cost).lstrip('-+')} paid)"
                            if cost and inst.asset != "future" else "")
                         )
                mtf_chart(mpath, bars, sess, s0, pos, fill_states, all_events, clean, clock, tfs, ctx_tfs, extra)
                report["positions"][-1]["timeframes_chart"] = mpath.name

    # whole-day P/L curve across every position (for daily loss limits)
    day_worst = None
    if day_pnl_path:
        ends = sorted({b.end for (_, pr) in day_pnl_path for b in pr.und})
        for t in ends:
            tot_lo = 0.0
            for pos, pr in day_pnl_path:
                done = [f for f in pos.fills if f.time < t]
                if not done:
                    continue
                held = sum(f.sign * f.qty for f in done)
                cash = sum(pos.net(f) for f in done)
                if abs(held) > 1e-9:
                    rng = [(lo, hi) for (b, lo, hi) in pr.bar_ranges(t - timedelta(seconds=1), t)]
                    if not rng:
                        continue
                    lo, hi = rng[0]
                    cash += held * (lo if held > 0 else hi) * pos.inst.multiplier
                tot_lo += cash
            if day_worst is None or tot_lo < day_worst[0]:
                day_worst = (tot_lo, t)
    total = sum(p["pnl"] for p in report["positions"])
    report["net"] = total
    report["trade_date"] = fills[0].time.astimezone(ET).date().isoformat()
    report["max_daily_loss"] = args.max_daily_loss
    report["day_worst"] = None if not day_worst else {"pnl": day_worst[0], "at": clock.fmt(day_worst[1])}
    head = ["# TheStrat trade review", "",
            f"Positions: {len(report['positions'])}. Net: {money(total)}. Times {clock.abbr}"
            + ("" if clock.abbr == "ET" else " (ET)") + ".",
            ("" if not day_worst else
             f"Worst point of the day, realized plus open across all positions: {money(day_worst[0])} "
             f"(bar ending {clock.fmt(day_worst[1])})"
             + ("" if not args.max_daily_loss else
                (f". **Crossed the {money(-abs(args.max_daily_loss))} daily limit.**"
                 if day_worst[0] <= -abs(args.max_daily_loss) else
                 f", {money(day_worst[0] + abs(args.max_daily_loss))} from the {money(-abs(args.max_daily_loss))} daily limit."))),
            f"Underlying bars: `{Path(bars_path).name}`"
            + (f", daily: `{Path(args.daily).name}`" if args.daily else "")
            + (f", contract bars: `{Path(args.contract_bars).name}`" if args.contract_bars else "") + ".", ""]
    (out / "review.md").write_text("\n".join(head + md) + "\n")
    (out / "review.json").write_text(json.dumps(report, indent=2, default=str))
    print((out / "review.md").read_text())


# ----------------------------------------------------------------------------- chart

def chart(path, sbars, pos, levels, clean, clock, sess, chart_tf, all_bars, daily, candles="plain"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cb = aggregate(sbars, chart_tf, sess) if chart_tf != "base" else sbars
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=130)
    bg = "#0f0f0f"
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    prev = None
    xs = list(range(len(cb)))
    for i, b in enumerate(cb):
        tok = token(b, prev) if prev else ("1u" if above_open(b) else "1d")
        if candles == "strat":
            col = SUITE_COLORS.get(tok, "#9c9c9c")
        else:  # plain candles: green bull (close above open), red bear
            col = SUITE_COLORS["2u"] if above_open(b) else SUITE_COLORS["2d"]
        ax.vlines(i, b.low, b.high, color=col, linewidth=1)
        ax.add_patch(plt.Rectangle((i - 0.33, min(b.open, b.close)), 0.66, max(abs(b.close - b.open), 1e-6),
                                   facecolor=col, edgecolor=col))
        if prev and candles == "plain":  # bar type as a small label under the candle
            kind = tok.rstrip("ud") if tok[0] in "13" else tok
            ax.annotate(kind, (i, b.low), textcoords="offset points", xytext=(0, -9), ha="center",
                        color="#8a8a8a", fontsize=5.5)
        prev = b

    def x_of(t):
        for i, b in enumerate(cb):
            if b.start <= t < (cb[i + 1].start if i + 1 < len(cb) else b.end + timedelta(days=1)):
                return i
        return len(cb) - 1

    groups: dict = {}
    for f in pos.fills:  # one marker per chart bar and side
        if f.und is not None:
            groups.setdefault((x_of(f.time), f.sign), []).append(f)
    for (xi, sign), fs in groups.items():
        buy = sign > 0
        q = sum(f.qty for f in fs)
        avg = sum(f.qty * f.price for f in fs) / q
        y = sum(f.und for f in fs) / len(fs)
        ax.scatter(xi, y, marker="^" if buy else "v", s=90,
                   color="#2962ff" if buy else "#ffffff", edgecolors="#000000", zorder=5)
        ax.annotate(f"{'B' if buy else 'S'} {q:g} @ {avg:.4g}", (xi, y), textcoords="offset points",
                    xytext=(0, -16 if buy else 12), ha="center", color="#dddddd", fontsize=7)
    if clean:
        ev = clean["event"]
        bull = ev["dir"] == "BULL"
        xi = x_of(ev["time"])
        ax.hlines(ev["trigger"], xi - 0.5, len(cb) - 0.5, color="#4caf50" if bull else "#f23645", linewidth=1.2)
        ax.hlines(ev["stop_c1"], xi - 0.5, len(cb) - 0.5, color="#f23645" if bull else "#4caf50",
                  linewidth=1, linestyle="--")
        ax.text(len(cb) - 0.5, ev["trigger"], f" {ev['tf']} {ev['combo']} trigger {ev['trigger']:.2f}",
                color="#dddddd", fontsize=7, va="center")
        ax.text(len(cb) - 0.5, ev["stop_c1"], f" stop (C1) {ev['stop_c1']:.2f}", color="#dddddd", fontsize=7,
                va="center")
    step = max(1, len(cb) // 12)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([clock.fmt(b.start) for b in cb][::step], rotation=30, ha="right", fontsize=7, color="#cccccc")
    ax.tick_params(axis="y", colors="#cccccc", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#333333")
    note = ("candles in TheStrat Suite bar-type colors" if candles == "strat"
            else "green bull, red bear; bar type under each candle")
    tf_label = chart_tf if chart_tf != "base" else f"{int((cb[0].end - cb[0].start).total_seconds() // 60)}m"
    ax.set_title(f"{pos.inst.underlying} {tf_label} with {pos.inst.label()} fills ({note})", color="#dddddd", fontsize=9)
    ax.set_xlim(-1, len(cb) + 14)
    fig.tight_layout()
    fig.savefig(path, facecolor=bg)
    plt.close(fig)


def mtf_chart(path, bars, sess, s0, pos, fill_states, events, clean, clock, tfs, ctx_tfs, title_extra=""):
    """One image: a panel per timeframe (5m, 15m, 30m, 60m by default) with every fill numbered on it,
    the triggers near the trade, the clean Strat entry and its C1 stop, and a table of the state on
    each timeframe at each fill. Plain candles (green bull, red bear) with the bar type underneath."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    matplotlib.rcParams["text.parse_math"] = False   # dollar signs are text, not math

    BG, FG, MUTED, GRID = "#0f0f0f", "#e6e6e6", "#8a8a8a", "#2a2a2a"
    BULL_C, BEAR_C = SUITE_COLORS["2u"], SUITE_COLORS["2d"]
    fills = [f for f, _, _ in fill_states]
    first_t, last_t = fills[0].time, fills[-1].time
    rows = len(fill_states)
    fig = plt.figure(figsize=(16, 10.5 + 0.32 * max(0, rows - 4)), dpi=110)
    fig.patch.set_facecolor(BG)
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1, 1, 0.3 + 0.08 * rows], hspace=0.3, wspace=0.12,
                  left=0.05, right=0.97, top=0.9, bottom=0.03)
    fig.text(0.05, 0.965, f"{pos.inst.label()}  ·  {first_t.astimezone(ET):%a %b %-d, %Y}", color=FG,
             fontsize=17, weight="bold", va="center")
    if title_extra:
        fig.text(0.05, 0.935, title_extra, color=MUTED, fontsize=11, va="center")
    fig.text(0.97, 0.965, "#n = fill number (blue ▲ buy, white ▼ sell). Candles: green bull, red bear; "
             "bar type under each.", color=MUTED, fontsize=9, ha="right", va="center")

    for k, tf in enumerate(tfs[:4]):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        ax.set_facecolor(BG)
        agg = aggregate(bars, tf, sess)
        idx0 = next((i for i, b in enumerate(agg) if sess.start_of(b.start) == s0), None)
        if idx0 is None:
            continue
        sb = [b for b in agg if sess.start_of(b.start) == s0]
        prev0 = agg[idx0 - 1] if idx0 > 0 else None
        step = timedelta(minutes=TF_MIN[tf])
        lo_t, hi_t = sb[0].start, sb[-1].start + step
        if len(sb) > 40:   # zoom the fast timeframe to the trade
            lo_t = max(lo_t, first_t - 12 * step)
            hi_t = min(hi_t, last_t + 18 * step)
        view = [(i, b) for i, b in enumerate(sb) if lo_t <= b.start < hi_t]
        for j, (i, b) in enumerate(view):
            prev = sb[i - 1] if i > 0 else prev0
            col = BULL_C if above_open(b) else BEAR_C
            ax.vlines(j, b.low, b.high, color=col, linewidth=1)
            ax.add_patch(plt.Rectangle((j - 0.33, min(b.open, b.close)), 0.66,
                                       max(abs(b.close - b.open), 1e-6), facecolor=col, edgecolor=col))
            kind = token(b, prev) if prev else "?"
            kind = kind.rstrip("ud") if kind[0] in "13" else kind
            ax.annotate(kind, (j, b.low), textcoords="offset points", xytext=(0, -9), ha="center",
                        color=MUTED, fontsize=6.5)

        def x_of(t):
            for j, (i, b) in enumerate(view):
                if b.start <= t < b.start + step:
                    return j
            return None

        # the first trigger with the trade on this timeframe once the trade is on (not a gap-through)
        is_clean_tf = bool(clean) and clean["event"]["tf"] == tf
        if not is_clean_tf:
            nxt = [e for e in events if e["tf"] == tf and not e.get("gap") and e["dir"] == pos.direction
                   and e["time"] >= first_t - step]
            if nxt:
                e = nxt[0]
                j = x_of(e["time"])
                if j is not None:
                    c = BULL_C if e["dir"] == "BULL" else BEAR_C
                    ax.hlines(e["trigger"], j - 0.45, len(view) - 0.5, color=c, linewidth=1.2, alpha=0.9)
                    ax.annotate(f"{tf} trigger {e['combo']} {e['trigger']:.2f}, "
                                f"{clock.fmt(e['time']).split(' (')[0]}", (len(view) - 0.5, e["trigger"]),
                                textcoords="offset points", xytext=(-2, 4), ha="right", color=c, fontsize=8)
        if clean and clean["event"]["tf"] == tf:
            e = clean["event"]
            j = x_of(e["time"])
            if j is not None:
                c = BULL_C if e["dir"] == "BULL" else BEAR_C
                ax.hlines(e["trigger"], j - 0.45, len(view) - 0.5, color=c, linewidth=1.8)
                ax.hlines(e["stop_c1"], j - 1.45, len(view) - 0.5, color=MUTED, linewidth=1, linestyle="--")
                ax.annotate(f"Strat entry: {e['combo']} {e['trigger']:.2f}, {clock.fmt(e['time']).split(' (')[0]}",
                            (len(view) - 0.5, e["trigger"]), textcoords="offset points", xytext=(-2, 4),
                            ha="right", color=c, fontsize=8, weight="bold")
                ax.annotate(f"C1 stop {e['stop_c1']:.2f}", (len(view) - 0.5, e["stop_c1"]),
                            textcoords="offset points", xytext=(-2, -10), ha="right", color=MUTED, fontsize=7.5)

        groups: dict = {}
        for n, f in enumerate(fills, 1):   # one marker per bar and side, numbered by fill order
            j = x_of(f.time)
            if j is not None and f.und is not None:
                groups.setdefault((j, f.sign), []).append((n, f))
        for (j, sign), nf in groups.items():
            buy = sign > 0
            y = sum(f.und for _, f in nf) / len(nf)
            ax.scatter(j, y, marker="^" if buy else "v", s=80, color="#2962ff" if buy else "#ffffff",
                       edgecolors="#000000", zorder=6)
            ax.annotate("#" + ",".join(str(n) for n, _ in nf), (j, y), textcoords="offset points",
                        xytext=(0, -17 if buy else 10), ha="center", color="#0f0f0f", fontsize=7.5,
                        weight="bold", zorder=7,
                        bbox=dict(boxstyle="round,pad=0.2", fc="#2962ff" if buy else "#ffffff", ec="none"))
        st0 = fill_states[0][1].get(tf, {})
        sign = st0.get("sign")
        ax.set_title(tf, loc="left", color=FG, fontsize=12, weight="bold")
        ax.set_title(f"at fill 1: {st0.get('combo', '-')}"
                     + ("" if sign is None else ("  above open" if sign else "  below open")),
                     loc="right", fontsize=9, color=MUTED if sign is None else (BULL_C if sign else BEAR_C))
        n_ticks = 6
        stp = max(1, len(view) // n_ticks)
        ax.set_xticks(range(0, len(view), stp))
        ax.set_xticklabels([clock.fmt(view[j][1].start).split(" (")[0] for j in range(0, len(view), stp)],
                           fontsize=7.5, color=MUTED)
        ax.tick_params(axis="y", colors=MUTED, labelsize=7.5)
        ax.set_xlim(-1, len(view))
        for sp in ax.spines.values():
            sp.set_color(GRID)

    # state at each fill on every timeframe
    tab = fig.add_subplot(gs[2, :])
    tab.set_axis_off()
    cols = tfs + ctx_tfs
    head = ["#", "Fill"] + [c + (" (context)" if c in ctx_tfs else "") for c in cols] + ["Continuity"]
    xs_col = [0.0, 0.03] + [0.3 + 0.115 * i for i in range(len(cols))] + [0.3 + 0.115 * len(cols)]
    y = 0.92
    for x, h in zip(xs_col, head):
        tab.text(x, y, h, color=MUTED, fontsize=9, transform=tab.transAxes, va="top")
    for n, (f, st, cont) in enumerate(fill_states, 1):
        y -= 0.78 / (rows + 1)
        side = "BUY" if f.sign > 0 else "SELL"
        tab.text(xs_col[0], y, str(n), color=FG, fontsize=9.5, weight="bold", transform=tab.transAxes, va="top")
        tab.text(xs_col[1], y, f"{clock.fmt(f.time)}  {side} {f.qty:g} @ {f.price:g}"
                 + (f"  ({pos.inst.underlying} {f.und:.2f})" if f.und else ""),
                 color=FG, fontsize=9, transform=tab.transAxes, va="top")
        for i, c in enumerate(cols):
            s_ = st.get(c, {})
            sg = s_.get("sign")
            tab.text(xs_col[2 + i], y, s_.get("combo", "-") + ("" if sg is None else (" ↑" if sg else " ↓")),
                     color=FG if sg is None else (BULL_C if sg else BEAR_C), fontsize=9, family="monospace",
                     transform=tab.transAxes, va="top")
        tab.text(xs_col[-1], y, cont, color=FG, fontsize=9, transform=tab.transAxes, va="top")
    tab.text(0, 0.0, "↑ / ↓: the forming bar is above / below its open at the fill (only bars closed by then are "
             "used). ? = no prior bar to compare (load the prior session). Not advice.",
             color=MUTED, fontsize=8, transform=tab.transAxes, va="bottom")
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


# ----------------------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fills", required=True,
                    help="A broker export as-is (Schwab, IBKR, Tradovate, NinjaTrader, Webull, Robinhood, Public, "
                         "Alpaca) or a CSV with time, symbol, side, qty, price [, fees, net]")
    ap.add_argument("--fills-tz", default="ET", help="Zone for fill times that carry none (ET, PT, CT, UTC)")
    ap.add_argument("--bars", help="Underlying intraday bars (CSV time,open,high,low,close or Public/TradingView JSON)")
    ap.add_argument("--daily", help="Daily bars for prior days (for the Day timeframe's C1/C2 and prior close)")
    ap.add_argument("--contract-bars", help="Intraday bars for the option contract itself (real marks)")
    ap.add_argument("--fetch", choices=["yfinance"], help="Download underlying bars instead of --bars")
    ap.add_argument("--no-auto-context", action="store_true",
                    help="Don't fill in missing prior-session or daily bars from Yahoo Finance")
    ap.add_argument("--yf-symbol", help="Yahoo symbol to fetch (e.g. SPY, ES=F, NQ=F)")
    ap.add_argument("--interval", default="5m", help="Fetch interval (1m or 5m)")
    ap.add_argument("--symbol", help="Only review positions on this symbol or underlying")
    ap.add_argument("--asset", choices=["option", "stock", "future"], help="Force asset type")
    ap.add_argument("--multiplier", type=float, help="Force contract multiplier")
    ap.add_argument("--session", default="auto", choices=["auto", "rth", "futures"])
    ap.add_argument("--session-hours", help="Custom RTH window in ET, e.g. 09:30-16:00")
    ap.add_argument("--tfs", default="5m,15m,30m,60m",
                    help="The timeframe view: state at each fill, continuity and flags")
    ap.add_argument("--context-tfs", default="D",
                    help="Extra timeframes shown for context only, not counted in continuity ('' for none)")
    ap.add_argument("--entry-tf", default="30m", help="Timeframe whose trigger defines the clean Strat entry")
    ap.add_argument("--clean-entry", help="Pin the clean entry to the first --entry-tf trigger at/after this time")
    ap.add_argument("--t1", type=float, help="Override first target (underlying price)")
    ap.add_argument("--mark", help="Mark time for hold/runner rows (default: last bar of session)")
    ap.add_argument("--or-minutes", type=int, default=30, help="Opening range length in minutes")
    ap.add_argument("--runner-fraction", type=float, default=0.25)
    ap.add_argument("--caution-until", default="", help="ET time before which entries get EARLY_SESSION; off unless the trader "
                                                       "has this rule (e.g. 09:45)")
    ap.add_argument("--max-daily-loss", type=float, help="Daily loss limit to test the worst point against")
    ap.add_argument("--triggers-window", type=float, default=3, help="Only list triggers within N hours of entry (0 = all)")
    ap.add_argument("--trail-tf", default="60m", help="Runner trails under each completed bar of this timeframe")
    ap.add_argument("--min-target-r", type=float, default=1.0,
                    help="Clean plan first target: nearest magnitude/reference level at least this many R away")
    ap.add_argument("--display-tz", default="America/Los_Angeles")
    ap.add_argument("--chart", action="store_true", help="Write a PNG chart (needs matplotlib)")
    ap.add_argument("--chart-tf", default="base", help="Chart candle timeframe: base, 5m, 15m, ...")
    ap.add_argument("--candles", default="plain", choices=["plain", "strat"],
                    help="plain: green bull, red bear, bar type labeled; strat: Suite bar-type colors")
    ap.add_argument("--out", default="strat_review_out")
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
