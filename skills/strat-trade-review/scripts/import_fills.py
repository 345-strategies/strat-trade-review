#!/usr/bin/env python3
"""Turn a broker's own export into the normalized fills CSV strat_review.py reads.

Drop in the file exactly as the broker gave it. The format is detected from its
headers (or JSON shape); no editing needed.

  python3 import_fills.py my_export.csv            # prints the normalized CSV
  python3 import_fills.py my_export.csv -o fills.csv
  python3 import_fills.py my_export.csv --tz PT    # zone of the export's times, if it has none

Recognized: Schwab / thinkorswim (Account Trade History), Interactive Brokers (Flex Query
or Trade Log CSV), Tradovate (Orders / Fills), NinjaTrader (Executions), Webull (order
history), Robinhood (activity report), Public (history CSV or the Public API / MCP
get_history JSON), Alpaca (activities JSON), and any CSV that already has
time / symbol / side / qty / price columns.

Normalized columns: time, symbol, side, qty, price, fees, net
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def num(x) -> float:
    """'$1,234.50', '(225.96)', '@1.13', '-0.62' -> float."""
    s = str(x or "").strip().replace("$", "").replace(",", "").replace("@", "")
    if not s:
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    v = float(s)
    return -v if neg else v


def occ(root: str, exp: datetime, cp: str, strike: float) -> str:
    return f"{root.upper()}{exp:%y%m%d}{cp.upper()[0]}{int(round(strike * 1000)):08d}"


def stamp(s: str, tz: str) -> str:
    """Keep the broker's time text, adding the zone only when it has none."""
    s = s.strip()
    if re.search(r"(Z|[+-]\d{2}:?\d{2}|\b(ET|EST|EDT|PT|PST|PDT|CT|CST|CDT|UTC|GMT))$", s):
        return s
    return f"{s} {tz}"


def row(time, symbol, side, qty, price, fees=0.0, net=""):
    return dict(time=time, symbol=symbol, side=side, qty=f"{abs(qty):g}", price=f"{price:g}",
                fees=f"{fees:g}", net="" if net == "" else f"{net:g}")


def lower_keys(r: dict) -> dict:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}


# ----------------------------------------------------------------------------- CSV formats

def schwab(text: str, tz: str):
    """thinkorswim Account Statement: the 'Account Trade History' section."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.lstrip(",").startswith("Exec Time"))
    body = []
    for l in lines[start:]:
        if not l.strip():
            break
        body.append(l.lstrip(","))
    out, last_time = [], ""
    for r in csv.DictReader(body):
        r = lower_keys(r)
        t = r.get("exec time") or last_time
        last_time = t
        q = num(r.get("qty"))
        if not q:
            continue
        side = "BUY" if q > 0 else "SELL"
        sym = r.get("symbol", "")
        typ = r.get("type", "").upper()
        price = num(r.get("price"))
        if typ in ("CALL", "PUT"):
            d, mon, yy = r["exp"].split()[:3]
            exp = datetime(2000 + int(yy[-2:]), MONTHS[mon[:3].upper()], int(d))
            sym = occ(sym, exp, typ, num(r["strike"]))
        out.append(row(stamp(t, tz), sym, side, q, price))
    return out


def ibkr(rows: list[dict], tz: str):
    out = []
    for r in rows:
        r = lower_keys(r)
        if r.get("levelofdetail", "EXECUTION").upper() not in ("EXECUTION", ""):
            continue
        q = num(r.get("quantity"))
        if not q:
            continue
        side = r.get("buy/sell", "").upper() or ("BUY" if q > 0 else "SELL")
        t = r.get("datetime") or r.get("date/time") or f"{r.get('tradedate', '')} {r.get('tradetime', '')}"
        t = t.replace(";", " ").replace(",", "")
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2}) (\d{2}):?(\d{2}):?(\d{2})", t.strip())
        if m:
            t = f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}:{m[6]}"
        sym = r.get("symbol", "")
        if r.get("assetclass", "").upper() == "OPT" and r.get("expiry") and r.get("strike"):
            e = re.sub(r"\D", "", r["expiry"])
            sym = occ(r.get("underlyingsymbol") or sym.split()[0], datetime.strptime(e, "%Y%m%d"),
                      r.get("put/call", "C"), num(r["strike"]))
        comm = num(r.get("ibcommission") or r.get("commission") or r.get("comm/fee"))
        out.append(row(stamp(t, tz), sym.replace(" ", "") if re.search(r"\d{6}[CP]\d{8}", sym.replace(" ", "")) else sym,
                       "BUY" if side.startswith("B") else "SELL", q,
                       num(r.get("tradeprice") or r.get("t. price") or r.get("price")), -comm))
    return out


def tradovate(rows, tz):
    out = []
    for r in rows:
        r = lower_keys(r)
        if r.get("status") and r["status"].lower() not in ("filled", "partfilled", " filled"):
            continue
        q = num(r.get("filledqty") or r.get("filled qty") or r.get("quantity") or r.get("qty"))
        if not q:
            continue
        t = r.get("fill time") or r.get("timestamp") or r.get("date")
        out.append(row(stamp(t, tz), r.get("contract") or r.get("product"),
                       "BUY" if r.get("b/s", "").strip().upper().startswith("B") else "SELL", q,
                       num(r.get("avgprice") or r.get("avg fill price") or r.get("price"))))
    return out


def ninjatrader(rows, tz):
    out = []
    for r in rows:
        r = lower_keys(r)
        q = num(r.get("quantity"))
        if not q:
            continue
        act = r.get("action", "").upper()
        out.append(row(stamp(r["time"], tz), r["instrument"], "BUY" if act.startswith("B") else "SELL", q,
                       num(r.get("price")), num(r.get("commission"))))
    return out


def webull(rows, tz):
    out = []
    for r in rows:
        r = lower_keys(r)
        if r.get("status", "Filled").lower() != "filled":
            continue
        q = num(r.get("filled") or r.get("total qty"))
        if not q:
            continue
        out.append(row(stamp(r.get("filled time") or r.get("placed time"), tz), r["symbol"],
                       "BUY" if r.get("side", "").upper().startswith("B") else "SELL", q,
                       num(r.get("avg price") or r.get("price"))))
    return out


def robinhood(rows, tz):
    out, warned = [], False
    for r in rows:
        r = lower_keys(r)
        code = r.get("trans code", "").upper()
        if code not in ("BTO", "STC", "STO", "BTC", "BUY", "SELL"):
            continue
        desc = r.get("description", "")
        sym = r.get("instrument", "")
        m = re.search(r"(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$?([\d.,]+)", desc, re.I)
        if m:
            sym = occ(m[1], datetime.strptime(m[2], "%m/%d/%Y"), m[3], num(m[4]))
        t = r.get("activity date", "")
        if not re.search(r"\d:\d", t):
            if not warned:
                print("warning: Robinhood activity reports have no time of day. Times are set to 09:30 ET; "
                      "fix them from the app's order details before reviewing.", file=sys.stderr)
                warned = True
            t = f"{t} 09:30:00"
        out.append(row(stamp(t, tz), sym, "BUY" if code in ("BTO", "BTC", "BUY") else "SELL",
                       num(r.get("quantity")), num(r.get("price")), 0.0, num(r.get("amount"))))
    return out


def public_csv(rows, tz):
    out = []
    for r in rows:
        r = lower_keys(r)
        if r.get("type", "TRADE").upper() not in ("TRADE", "BUY", "SELL"):
            continue
        q = num(r.get("quantity"))
        if not q:
            continue
        price = num(r.get("price")) if r.get("price") else _price_from(r.get("description", ""), r)
        out.append(row(stamp(r.get("timestamp") or r.get("date"), tz), r["symbol"], r["side"].upper(), q,
                       price, 0.0, num(r["netamount"]) if r.get("netamount") else ""))
    return out


def _price_from(desc: str, r: dict) -> float:
    m = re.search(r"\bat\s+\$?([\d.,]+)", desc)
    return num(m[1]) if m else 0.0


def generic(rows, tz):
    out = []
    for r in rows:
        lr = lower_keys(r)
        g = lambda *ks: next((lr[k] for k in ks if lr.get(k)), "")  # noqa: E731
        t, sym = g("time", "timestamp", "datetime", "date/time", "date"), g("symbol", "contract", "instrument", "ticker")
        q, px = g("qty", "quantity", "size", "shares", "contracts"), g("price", "fill price", "avg price")
        if not (t and sym and q and px):
            continue
        side = g("side", "action", "b/s", "buy/sell").upper()
        qv = num(q)
        side = "BUY" if (side.startswith("B") or (not side and qv > 0)) else "SELL"
        out.append(row(stamp(t, tz), sym, side, qv, num(px), num(g("fees", "commission")),
                       num(g("net")) if g("net") else ""))
    return out


# ----------------------------------------------------------------------------- JSON formats

def from_json(data, tz):
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        data = json.loads(data["result"])  # MCP wrapper
    if isinstance(data, dict) and "transactions" in data:  # Public API / MCP get_history
        out = []
        for t in data["transactions"]:
            if t.get("type") != "TRADE":
                continue
            q = num(t.get("quantity"))
            mult = 100 if t.get("securityType") == "OPTION" else 1
            price = _price_from(t.get("description", ""), t) or abs(num(t.get("principalAmount"))) / (q * mult)
            out.append(row(t["timestamp"], t["symbol"], t["side"].upper(), q, price, 0.0, num(t["netAmount"])))
        return out
    if isinstance(data, list) and data and "transaction_time" in data[0]:  # Alpaca FILL activities
        return [row(a["transaction_time"], a["symbol"], a["side"].upper(), num(a["qty"]), num(a["price"]))
                for a in data if a.get("activity_type", "FILL") == "FILL"]
    raise SystemExit("Unrecognized JSON. Expected Public get_history or Alpaca activities.")


# ----------------------------------------------------------------------------- detection

def detect(text: str) -> str:
    head = text[:4000].lower()
    if "account trade history" in head or re.search(r"^,?exec time,spread,side,qty", head, re.M):
        return "schwab"
    if "ibcommission" in head or "tradeprice" in head or ("buy/sell" in head and "assetclass" in head):
        return "ibkr"
    if "filledqty" in head or ("b/s" in head and "contract" in head and "avgprice" in head):
        return "tradovate"
    if re.search(r"^instrument,action,quantity,price,time", head, re.M):
        return "ninjatrader"
    if "filled time" in head and "avg price" in head:
        return "webull"
    if "trans code" in head and "activity date" in head:
        return "robinhood"
    if "netamount" in head and "description" in head:
        return "public_csv"
    return "generic"


def convert(path: str, tz: str = "ET") -> tuple[str, list[dict]]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip().startswith(("{", "[")):
        return "json", from_json(json.loads(text), tz)
    kind = detect(text)
    if kind == "schwab":
        return kind, schwab(text, tz)
    rows = list(csv.DictReader(io.StringIO(text)))
    return kind, {"ibkr": ibkr, "tradovate": tradovate, "ninjatrader": ninjatrader, "webull": webull,
                  "robinhood": robinhood, "public_csv": public_csv, "generic": generic}[kind](rows, tz)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="The broker's export file, unedited")
    ap.add_argument("-o", "--out", help="Write the normalized CSV here (default: stdout)")
    ap.add_argument("--tz", default="ET", help="Zone for times that carry none (ET, PT, CT, UTC). Default ET")
    a = ap.parse_args(argv)
    kind, rows = convert(a.export, a.tz)
    f = open(a.out, "w", newline="") if a.out else sys.stdout
    w = csv.DictWriter(f, fieldnames=["time", "symbol", "side", "qty", "price", "fees", "net"])
    w.writeheader()
    w.writerows(rows)
    print(f"detected {kind}: {len(rows)} fills", file=sys.stderr)


if __name__ == "__main__":
    main()
