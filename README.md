# Trading Journal

A personal trading journal built with Django for tracking options trades.

## Features

- Trade log with filtering, CSV import/export, and R:R calculation
- Session-based daily view with pre-trade checklist and psych tracking
- Calendar with green/red P&L backgrounds
- Analytics dashboard (win rate by tag, P&L by day of week, drawdown, etc.)
- IBKR/TWS integration for live Greeks
- Performance review and goal tracking

## Stack

- Python 3.11 · Django 5.2 · SQLite
- Tailwind CSS · Alpine.js · HTMX · Chart.js

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

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).
