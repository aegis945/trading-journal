# Trading Journal

A personal options trading journal built with Django. Dark UI, runs entirely on your local machine.

## Features

### Trade Log

- Add, edit, and delete trades with full options metadata (strike, expiry, type, quantity, entry/exit prices and times)
- **Paper trade support** — flag any trade as paper; P&L shown in yellow throughout the app, excluded from real performance stats
- Filter by date range, option type, trade type, status, rule review, and tag
- Rule adherence tracking per trade (followed / broke rules, rule break context and tags)
- Screenshot attachments per trade
- CSV import (upload → preview → confirm) and CSV export
- Quick-add trade form accessible from anywhere

### Sessions

- Automatic session creation on dashboard visit for today's market date
- Pre-market plan, psychological state / bias notes, post-session reflection
- Live per-session checklist (toggle items via HTMX without page reload)
- Session detail splits **Live trades** and **Paper trades** into separate sections
- Session P&L header only shown when trades exist; paper P&L annotated in yellow
- Weekend and market-holiday sessions blocked from creation

### Calendar

- Monthly grid with green/red cell tinting driven by **real** P&L only
- Paper P&L shown as a yellow annotation below the daily real P&L
- Monthly total footer

### Analytics

- **Overview charts** — cumulative P&L, win rate by tag, P&L by time of day, P&L by weekday, psych state vs outcome, delta vs P&L, streak, drawdown, setup quality, duration vs P&L
- **Monthly Performance table** — real trades + paper sub-row per month, win rate, avg R:R
- **Weekly Review** — real-only headline stats (P&L, win rate, trade count, avg R:R); paper count and paper P&L shown as yellow annotations; best/worst trades with real-trade priority; session-by-session timeline; rule adherence summary; weekly note prompt

### Journal

- Free-form markdown entries (powered by EasyMDE)
- Entry types: trade note, weekly review note, general note
- Link entries to specific trades or sessions

### Goals

- Quantitative goals (e.g. monthly P&L target) with progress bars
- Process goals (e.g. rule follow rate, session prep completion) auto-calculated from trade data
- Optional end date; delete confirmation

### IBKR / TWS Integration

- Connect to Interactive Brokers TWS via `ib-insync`
- Live option chain viewer with real-time Greeks
- Connection status indicator; configurable host/port/client-id

### Option Calculator

- Black-Scholes based theoretical pricing and Greeks

### Settings

- Display currency preference with live exchange rate fetch (falls back to saved rate)
- Checklist template manager — create, edit, reorder, and activate templates

## Stack

- **Python 3.11.14** · **Django 5.2.12** · SQLite
- Tailwind CSS (CDN JIT) · Alpine.js · HTMX · Chart.js · Lucide Icons
- EasyMDE · IBM Plex Mono · `holidays` · `ib-insync` · Pillow · NumPy

## Setup

```bash
git clone https://github.com/aegis945/trading-journal
cd trading-journal
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set SECRET_KEY
python manage.py migrate
python manage.py seed_data   # optional sample data
python manage.py runserver 8001
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001).

## Tests

```bash
python manage.py test journal analytics
```

85 tests covering models, views, templates, analytics endpoints, and paper-trade separation.
