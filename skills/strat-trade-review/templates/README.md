# Card templates

`share_post.py` draws the two share images from these HTML files:

| File | Image | Size |
|---|---|---|
| `card.html` | `card.png`: the P/L-style scorecard card (big %, Strat scorecard, alternatives, reflection) | 1200x675, rendered at 2x |
| `timeframes.html` | `timeframes.png`: 5m / 15m / 30m / 60m with every fill numbered, triggers, the Strat entry and C1 stop, and the state at each fill | 1600x1040, rendered at 2x |

They are rendered with a headless Chrome, Chromium or Edge (`scripts/render_html.py` finds one; set `STRAT_CHROME` to point at it). With no browser, `share_post.py` falls back to the matplotlib versions, which ignore templates.

## Customizing

Pick the smallest change that does what you want.

**1. Flags, no editing.**

```bash
python3 scripts/share_post.py --review out --lesson "In my words" --setup "Reversal, 30m F2d-2u" \
  --handle @me --number-color white
```

`--number-color white` makes the big % white instead of green on a gain and red on a loss.

**2. Your own colors and fonts.** Copy this folder somewhere of your own, change the variables in the `:root { ... }` block at the top of each file, and point at it:

```bash
cp -r templates ~/my-strat-cards
# edit ~/my-strat-cards/card.html  (:root { --bg: ...; --with: ...; --font-display: ... })
python3 scripts/share_post.py --review out --templates ~/my-strat-cards
```

A file you leave out of your folder falls back to the built-in one, so you can customize only `card.html`. Keep the conventions: green and red mean bull and bear (and, on the headline only, gain and loss); the scorecard's WITH and AGAINST use blue and amber with an icon and a label.

**3. Your own layout.** Edit the HTML and CSS freely: move sections, drop the alternatives, add a logo, change the size in `<meta name="card-size" content="1200x675">`. You can also paste a template into Claude Design or any HTML editor, adjust it visually, and save it back. Two things must stay:

- `<meta name="card-size" content="WIDTHxHEIGHT">`
- `<script id="card-data" type="application/json">{}</script>`: the data goes here.

**Re-render without re-running the review.** `share_post.py` saves the data next to the images, so you can iterate on a template on its own:

```bash
python3 scripts/render_html.py --template ~/my-strat-cards/card.html --data out/share/card.json --out card.png
```

Or open the template in a browser with the data pasted into the `card-data` tag.

Options a template reads from `options` in the data: `numberColor` (`gainloss` or `white`), `maxAlternatives` (card, default 5), `showAlternatives` (card), `barTypes` (timeframes, `false` hides the labels under candles), `showQty` (timeframes, default off), `maxFillRows` (timeframes, default 6).

## What's in the data

Nothing personal is shown: no dollar amounts, no loss limits or rules (those stay in the trader's private journal), and fill quantities only with `showQty`.

`card.json`:

| Field | Example |
|---|---|
| `title`, `direction`, `date`, `tags`, `handle` | `"SPY 775C"`, `"BULL"`, `"Wed Oct 7, 2026"`, `["0DTE", "Reversal, 30m F2d-2u"]`, `""` |
| `hero` | `{"value": "+25%", "label": "Return on premium", "sign": 1}` (futures: R) |
| `stats` | `[{"label": "R multiple", "value": "+0.5R"}, {"label": "Avg in", "value": "0.92"}, ...]` |
| `entry` | `{"continuity": "Conflict", "states": [{"tf": "15m", "combo": "F2d-F2u", "sign": true}, ...]}` (`sign`: true above its open, false below, null not yet known) |
| `context` | `["gap down 0.4%"]`, and on Mondays a note that the week and the day are the same candle |
| `score` | `{"with_chart": 1, "graded": 4, "items": [{"ok": false, "name": "Entered as the trigger failed", "detail": "..."}]}` (`ok`: true WITH, false AGAINST, null JUDGMENT) |
| `alternatives` | `[{"label": "What you did", "text": "+25%  +0.5R", "value": 25.0, "actual": true}, ...]` (`value` sizes the bar) |
| `altColumns`, `reflection`, `footer`, `options` | `"Return · R"`, the trader's words, footer text, see above |

`timeframes.json` has the same `title`, `direction`, `date`, `tags`, `handle`, `hero`, `heroSub` and `options`, plus:

| Field | Example |
|---|---|
| `tz`, `tfs`, `ctx_tfs`, `underlying` | `"PT"`, `["5m", "15m", "30m", "60m"]`, `["D"]`, `"SPY"` |
| `panels[]` | `{"tf": "30m", "state": {"combo": "2d-F2d", "sign": false}, "candles": [[open, high, low, close, "F2d", "7:00"], ...], "marks": [[fill_no, candle_index, "BUY", underlying_price], ...], "trigger": {"j": 2, "px": 775.28, "label": "..."} or null, "clean": {"j": 3, "px": 774.82, "c1": 773.61, "label": "...", "slabel": "..."} or null}` |
| `fills[]` | `{"n": 1, "time": "7:25 PT (10:25 ET)", "side": "BUY", "qty": 2, "price": 1.13, "und": 774.74, "continuity": "Conflict", "states": [{"tf": "5m", "combo": "F2u-new", "sign": null}, ...]}` |

Prices and bar types come straight from the review's bars; the templates only draw them.
