"""
management/commands/seed_data.py

Populate the database with 30 days of realistic SPX trading data.
Usage:  python manage.py seed_data [--reset]
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from journal.models import (
    TradingSession, Trade, PreTradeChecklist, JournalEntry, PerformanceGoal,
    MarketBias, OptionType, TradeType, TradeStatus, EntryType,
    GoalMetric, GoalPeriod, GoalStatus,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGIES = [
    ["momentum"],
    ["VWAP reclaim"],
    ["mean reversion"],
    ["0dte scalp"],
    ["gap fill", "momentum"],
    ["VWAP rejection"],
    ["trend follow"],
    ["news catalyst"],
    ["opening range", "breakout"],
    ["earnings IV crush"],
]

SETUPS = [1, 2, 3, 3, 4, 4, 4, 5, 5, 5]

BIASES = [MarketBias.BULLISH, MarketBias.BEARISH, MarketBias.NEUTRAL]

ENTRY_TYPES = [
    EntryType.OBSERVATION,
    EntryType.LESSON,
    EntryType.MARKET_NOTE,
    EntryType.RULE,
]

JOURNAL_TITLES_OBSERVATIONS = [
    "VIX spike correlated with bad fills",
    "Best trades came after 10am settle",
    "Opening 15 minutes too choppy for entries",
    "IV rank above 30 improved premium",
    "Followed plan perfectly — result was positive",
]

JOURNAL_TITLES_LESSONS = [
    "Stopped out too early — let winner run",
    "Sized too large on a low-conviction setup",
    "Do not trade into FOMC minutes",
    "Always set hard SL before entry",
    "Averaging down on losing 0DTE is a mistake",
]

JOURNAL_TITLES_MARKET = [
    "SPX held 50-day MA cleanly today",
    "VIX compressed before Fed decision",
    "Market opened gap-up, faded all gains",
    "Strong up-day with above-average volume",
    "Range-bound day: 20-pt SPX range",
]

JOURNAL_TITLES_RULES = [
    "Rule: never hold through the lunch hour",
    "Rule: max 2 contracts per trade",
    "Rule: exit if cost basis doubles against me",
    "Rule: no trades in final 30 minutes",
    "Rule: only trade A/B setups rated ≥3",
]

TITLE_MAP = {
    EntryType.OBSERVATION: JOURNAL_TITLES_OBSERVATIONS,
    EntryType.LESSON:      JOURNAL_TITLES_LESSONS,
    EntryType.MARKET_NOTE: JOURNAL_TITLES_MARKET,
    EntryType.RULE:        JOURNAL_TITLES_RULES,
}

CONTENT_TAILS = [
    "\n\nThis observation held across multiple sessions. Needs further validation.",
    "\n\nWill track this pattern for the next two weeks.",
    "\n\nCorrelates with elevated VIX and pre-FOMC jitter.",
    "\n\nAdjusting position sizing rules accordingly.",
    "",
]

CHECKLIST_ITEMS = [
    {"id": "mc1", "category": "Market Context", "label": "Check overnight futures & gap direction", "required": True},
    {"id": "mc2", "category": "Market Context", "label": "Review VIX level (>20 = reduce size)", "required": True},
    {"id": "mc3", "category": "Market Context", "label": "Note any scheduled macro events (FOMC, CPI, etc.)", "required": True},
    {"id": "mc4", "category": "Market Context", "label": "Identify key support/resistance levels on SPX", "required": False},
    {"id": "rc1", "category": "Risk Check", "label": "Max 2 contracts per trade confirmed", "required": True},
    {"id": "rc2", "category": "Risk Check", "label": "Hard stop-loss level set before entry", "required": True},
    {"id": "rc3", "category": "Risk Check", "label": "Daily max loss < $500", "required": True},
    {"id": "rc4", "category": "Risk Check", "label": "No averaging down on losing 0DTE", "required": True},
    {"id": "ms1", "category": "Mental State", "label": "Slept ≥6 hours", "required": False},
    {"id": "ms2", "category": "Mental State", "label": "No revenge trading after a losing day", "required": True},
    {"id": "ms3", "category": "Mental State", "label": "Not emotionally disturbed (news, stress, etc.)", "required": True},
    {"id": "ms4", "category": "Mental State", "label": "Reviewed yesterday's trades", "required": False},
]


def weekdays_back(n: int, reference: date) -> list[date]:
    """Return the last n weekday dates before (and including) reference."""
    days = []
    d = reference
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d -= timedelta(days=1)
    return days


class Command(BaseCommand):
    help = 'Seed the database with 30 days of sample SPX 0DTE trading data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all existing journal data before seeding',
        )

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Deleting existing data…')
            JournalEntry.objects.all().delete()
            Trade.objects.all().delete()
            TradingSession.objects.all().delete()
            PreTradeChecklist.objects.all().delete()
            PerformanceGoal.objects.all().delete()

        self.stdout.write('Creating checklist template…')
        cl, _ = PreTradeChecklist.objects.get_or_create(
            name='SPX 0DTE Standard',
            defaults={'items': CHECKLIST_ITEMS, 'is_active': True},
        )
        if not cl.is_active:
            cl.is_active = True
            cl.save()

        today = date.today()
        session_dates = weekdays_back(30, today)

        all_sessions = []
        all_trades   = []

        self.stdout.write('Creating sessions and trades…')
        random.seed(42)

        for d in session_dates:
            bias  = random.choice(BIASES)
            psych = random.randint(2, 5)
            vix   = round(random.uniform(13.5, 26.0), 2)

            session = TradingSession.objects.get_or_create(
                date=d,
                defaults={
                    'market_bias':        bias,
                    'psychological_state': psych,
                    'vix_level':          Decimal(str(vix)),
                    'market_open_notes':  f'VIX at {vix:.1f}, bias {bias}',
                    'session_notes':      'Post-session review pending.',
                },
            )[0]
            all_sessions.append(session)

            n_trades = random.randint(2, 4)
            for _ in range(n_trades):
                trade = self._make_trade(d, session)
                all_trades.append(trade)

        self.stdout.write('Creating journal entries…')
        all_entries = []
        for _ in range(random.randint(8, 12)):
            entry_type = random.choice(ENTRY_TYPES)
            titles     = TITLE_MAP[entry_type]
            title      = random.choice(titles)
            content    = title + random.choice(CONTENT_TAILS)
            session    = random.choice(all_sessions) if random.random() > 0.3 else None
            trade      = random.choice(all_trades)   if random.random() > 0.5 and all_trades else None
            tags       = random.sample(["spx", "0dte", "vix", "options", "discipline", "risk"], k=random.randint(1, 3))
            entry = JournalEntry.objects.create(
                title=title,
                content=content,
                entry_type=entry_type,
                tags=tags,
                session=session,
                trade=trade,
            )
            all_entries.append(entry)

        self.stdout.write('Creating performance goals…')
        PerformanceGoal.objects.get_or_create(
            title='Monthly Win Rate ≥ 55%',
            defaults={
                'description':   'Maintain at least 55% win rate over the month',
                'metric':        GoalMetric.WIN_RATE,
                'target_value':  Decimal('55.00'),
                'current_value': Decimal('58.30'),
                'period':        GoalPeriod.MONTHLY,
                'start_date':    today.replace(day=1),
                'end_date':      (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1),
                'status':        GoalStatus.ACTIVE,
            },
        )
        PerformanceGoal.objects.get_or_create(
            title='Avg R:R ≥ 1.5',
            defaults={
                'description':   'Average risk/reward ratio of at least 1.5 per month',
                'metric':        GoalMetric.AVG_RR,
                'target_value':  Decimal('1.50'),
                'current_value': Decimal('1.28'),
                'period':        GoalPeriod.MONTHLY,
                'start_date':    today.replace(day=1),
                'end_date':      (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1),
                'status':        GoalStatus.ACTIVE,
            },
        )

        totals = Trade.objects.filter(status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED]).count()
        wins   = Trade.objects.filter(pnl__gt=0).count()
        wr     = round(wins / totals * 100, 1) if totals else 0
        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Created {len(all_sessions)} sessions, {len(all_trades)} trades '
            f'({wins}/{totals} wins = {wr}% WR), {len(all_entries)} journal entries.'
        ))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_trade(self, trade_date: date, session: TradingSession) -> Trade:
        """Create a single realistic SPX trade."""
        spx_base = random.randint(4400, 5500)
        otm_offset = random.choice([-30, -20, -10, 10, 20, 30, 50])
        strike = Decimal(str(spx_base + otm_offset))

        is_call    = random.random() > 0.45
        trade_type = TradeType.LONG_CALL if is_call else TradeType.LONG_PUT
        opt_type   = OptionType.CALL      if is_call else OptionType.PUT
        qty        = random.randint(1, 2)

        # Entry: realistic premium
        entry_price = Decimal(str(round(random.uniform(0.5, 8.0), 2)))
        entry_hour  = random.randint(9, 13)
        entry_min   = random.randint(0, 59)
        entry_t     = time(entry_hour, entry_min)

        # Status
        roll = random.random()
        if roll < 0.05:
            status     = TradeStatus.OPEN
            exit_price = None
            exit_t     = None
        elif roll < 0.15:
            status     = TradeStatus.EXPIRED
            exit_price = None
            exit_t     = time(16, 0)
        else:
            status = TradeStatus.CLOSED
            outcome = random.choices(['win', 'loss'], weights=[55, 45])[0]
            if outcome == 'win':
                mult = Decimal(str(round(random.uniform(1.3, 3.0), 2)))
            else:
                mult = Decimal(str(round(random.uniform(0.1, 0.7), 2)))
            exit_price = (entry_price * mult).quantize(Decimal('0.01'))
            exit_hour  = min(entry_hour + random.randint(0, 3), 15)
            exit_min   = random.randint(0, 59)
            exit_t     = time(exit_hour, exit_min)

        tp1 = (entry_price * Decimal('2.0')).quantize(Decimal('0.01'))
        sl  = (entry_price * Decimal('0.5')).quantize(Decimal('0.01'))

        trade = Trade.objects.create(
            session     = session,
            trade_date  = trade_date,
            symbol      = 'SPX',
            option_type = opt_type,
            strike      = strike,
            expiry      = trade_date,
            quantity    = qty,
            entry_price = entry_price,
            exit_price  = exit_price,
            entry_time  = entry_t,
            exit_time   = exit_t,
            trade_type  = trade_type,
            status      = status,
            strategy_tags           = random.choice(STRATEGIES),
            setup_quality           = random.choice(SETUPS),
            planned_stop_loss       = sl,
            planned_take_profit_1   = tp1,
            delta_entry = Decimal(str(round(random.uniform(0.15, 0.65) * (1 if is_call else -1), 3))),
            theta_entry = Decimal(str(round(random.uniform(-0.50, -0.05), 3))),
            vega_entry  = Decimal(str(round(random.uniform(0.02, 0.30), 3))),
            iv_entry    = Decimal(str(round(random.uniform(0.15, 0.55), 4))),
            trade_notes = 'Seed trade — auto-generated.',
        )
        return trade
