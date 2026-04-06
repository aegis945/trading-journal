# Trading Journal

A personal options trading journal built with Django. Bloomberg-inspired dark UI, runs entirely on your local machine.

## Features

- **Trade log** — filter by date, type, status, tag; CSV import/export; R:R display
- **Sessions** — daily pre-market notes, psych/bias tracking, per-session checklist
- **Calendar** — monthly P&L overview with green/red cell tinting
- **Analytics** — cumulative P&L, win rate by tag, P&L by day of week, drawdown, monthly breakdown, performance review
- **Journal** — free-form markdown entries linked to trades or sessions
- **Goals** — set and track performance targets with progress bars
- **IBKR/TWS integration** — live Greeks via Interactive Brokers API, option chain viewer
- **Settings** — manage checklist templates

## Stack

- Python 3.11 · Django 5.2 · SQLite
- Tailwind CSS (CDN) · Alpine.js · HTMX · Chart.js · Lucide Icons
- EasyMDE (markdown editor) · IBM Plex Mono (numbers)

## Setup

```bash
git clone https://github.com/aegis945/trading-journal
cd trading-journal
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set SECRET_KEY
python manage.py migrate
python manage.py seed_data   # optional sample data
python manage.py runserver
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001).
