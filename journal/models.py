"""
journal/models.py

All domain models for the trading journal.
P&L and risk/reward are computed automatically in Trade.save().
All times stored in ET (America/New_York) — USE_TZ=True in settings.
"""

import datetime
import json
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
import holidays


def is_weekend_day(value):
    return value.weekday() >= 5


@lru_cache(maxsize=None)
def nyse_holidays_for_year(year):
    return holidays.financial_holidays('NYSE', years=[year])


def is_market_holiday(value):
    return value in nyse_holidays_for_year(value.year)


def market_holiday_name(value):
    if not is_market_holiday(value):
        return ''
    return nyse_holidays_for_year(value.year).get(value, 'Holiday')


def market_closed_label(value):
    if is_weekend_day(value):
        return 'Weekend'
    if is_market_holiday(value):
        return 'Holiday'
    return ''


def is_market_closed_day(value):
    return is_weekend_day(value) or is_market_holiday(value)


def previous_market_day(value):
    while is_market_closed_day(value):
        value -= datetime.timedelta(days=1)
    return value


class DisplayCurrency(models.TextChoices):
    USD = 'USD', 'US Dollar ($)'
    EUR = 'EUR', 'Euro (€)'


class AppPreferences(models.Model):
    display_currency = models.CharField(
        max_length=3,
        choices=DisplayCurrency.choices,
        default=DisplayCurrency.USD,
    )
    usd_to_eur_rate = models.DecimalField(
        'USD to EUR rate',
        max_digits=8,
        decimal_places=4,
        default=Decimal('0.9200'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Fetched automatically when P&L display currency is set to EUR.',
    )
    exchange_rate_updated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'App Preferences ({self.display_currency})'

    @property
    def pnl_currency_symbol(self):
        return '$' if self.display_currency == DisplayCurrency.USD else '€'

    def convert_pnl_value(self, value):
        amount = Decimal(str(value))
        if self.display_currency == DisplayCurrency.EUR:
            try:
                self.refresh_exchange_rate_if_needed()
            except (URLError, ValueError):
                pass
            amount = amount * self.usd_to_eur_rate
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def exchange_rate_is_stale(self):
        if not self.exchange_rate_updated_at:
            return True
        age = timezone.now() - self.exchange_rate_updated_at
        return age >= datetime.timedelta(hours=24)

    def fetch_usd_to_eur_rate(self):
        request = Request(
            'https://api.frankfurter.dev/v1/latest?from=USD&to=EUR',
            headers={'User-Agent': 'TradingJournal/1.0'},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        rate = payload.get('rates', {}).get('EUR')
        if rate is None:
            raise ValueError('USD to EUR rate missing from response')
        return Decimal(str(rate)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    def refresh_exchange_rate_if_needed(self, force=False):
        if self.display_currency != DisplayCurrency.EUR:
            return False
        if not force and not self.exchange_rate_is_stale():
            return False
        rate = self.fetch_usd_to_eur_rate()
        now = timezone.now()
        AppPreferences.objects.filter(pk=self.pk).update(
            usd_to_eur_rate=rate,
            exchange_rate_updated_at=now,
        )
        self.usd_to_eur_rate = rate
        self.exchange_rate_updated_at = now
        return True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


def get_app_preferences():
    prefs, _ = AppPreferences.objects.get_or_create(pk=1)
    return prefs


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class MarketBias(models.TextChoices):
    BULLISH = 'BULLISH', 'Bullish'
    BEARISH = 'BEARISH', 'Bearish'
    NEUTRAL = 'NEUTRAL', 'Neutral'


class OptionType(models.TextChoices):
    CALL = 'CALL', 'Call'
    PUT  = 'PUT',  'Put'


class TradeType(models.TextChoices):
    LONG_CALL = 'LONG_CALL', 'Long Call'
    LONG_PUT  = 'LONG_PUT',  'Long Put'
    CSP       = 'CSP',       'Cash-Secured Put'
    CC        = 'CC',        'Covered Call'


class TradeStatus(models.TextChoices):
    OPEN    = 'OPEN',    'Open'
    CLOSED  = 'CLOSED',  'Closed'
    EXPIRED = 'EXPIRED', 'Expired'


class EntryType(models.TextChoices):
    OBSERVATION  = 'OBSERVATION',  'Observation'
    LESSON       = 'LESSON',       'Lesson'
    MARKET_NOTE  = 'MARKET_NOTE',  'Market Note'
    RULE         = 'RULE',         'Rule'


class GoalMetric(models.TextChoices):
    WIN_RATE     = 'WIN_RATE',     'Win Rate (%)'
    AVG_RR       = 'AVG_RR',       'Avg Risk/Reward'
    MAX_DRAWDOWN = 'MAX_DRAWDOWN', 'Max Drawdown ($)'
    TOTAL_PNL    = 'TOTAL_PNL',    'Total P&L ($)'
    TRADE_COUNT  = 'TRADE_COUNT',  'Trade Count'


class GoalPeriod(models.TextChoices):
    WEEKLY    = 'WEEKLY',    'Weekly'
    MONTHLY   = 'MONTHLY',   'Monthly'
    QUARTERLY = 'QUARTERLY', 'Quarterly'


class GoalStatus(models.TextChoices):
    ACTIVE   = 'ACTIVE',   'Active'
    ACHIEVED = 'ACHIEVED', 'Achieved'
    MISSED   = 'MISSED',   'Missed'


# ---------------------------------------------------------------------------
# TradingSession
# ---------------------------------------------------------------------------

class TradingSession(models.Model):
    date                 = models.DateField(unique=True)
    market_open_notes    = models.TextField(blank=True)
    psychological_state  = models.IntegerField(
        null=True,
        blank=True,
        help_text='1 (worst) – 5 (best) mental state before trading',
    )
    psychological_notes  = models.TextField(blank=True)
    market_bias          = models.CharField(
        max_length=10,
        choices=MarketBias.choices,
        null=True,
        blank=True,
    )
    vix_level            = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    pre_trade_checklist  = models.JSONField(
        default=dict,
        help_text='Snapshot of checklist completion state for this day ({item_id: bool})',
    )
    session_notes        = models.TextField(blank=True, help_text='Post-session reflections')
    lessons_learned      = models.TextField(blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'Session {self.date}'

    @property
    def total_pnl(self):
        """Sum of P&L for all closed/expired trades in this session."""
        result = self.trades.filter(
            status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED]
        ).aggregate(total=models.Sum('pnl'))['total']
        return result or Decimal('0')

    @property
    def trade_count(self):
        return self.trades.count()

    @property
    def win_count(self):
        return self.trades.filter(pnl__gt=0).count()

    @property
    def is_pre_market_complete(self):
        return (
            bool(self.market_bias)
            and self.psychological_state is not None
            and bool((self.market_open_notes or '').strip())
        )

    @property
    def has_post_session_reflection(self):
        return bool(
            (self.session_notes or '').strip()
            or (self.lessons_learned or '').strip()
        )
# ---------------------------------------------------------------------------
# PreTradeChecklist (template definition)
# ---------------------------------------------------------------------------

class PreTradeChecklist(models.Model):
    name       = models.CharField(max_length=120)
    items      = models.JSONField(
        default=list,
        help_text='List of {id, label, category} dicts',
    )
    is_active  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_active', 'name']

    def __str__(self):
        return f'{self.name}{"  [active]" if self.is_active else ""}'

    def save(self, *args, **kwargs):
        # Enforce single active template
        if self.is_active:
            PreTradeChecklist.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------

_MULTIPLIER = Decimal('100')  # SPX options: 100 shares per contract


class Trade(models.Model):
    session     = models.ForeignKey(
        TradingSession, on_delete=models.CASCADE,
        related_name='trades', null=True, blank=True,
    )
    trade_date  = models.DateField()
    symbol      = models.CharField(max_length=10, default='SPX')
    option_type = models.CharField(max_length=4, choices=OptionType.choices)
    strike      = models.DecimalField(max_digits=10, decimal_places=2)
    expiry      = models.DateField()
    quantity    = models.IntegerField()
    entry_price = models.DecimalField(max_digits=10, decimal_places=4)
    exit_price  = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    entry_time  = models.TimeField()
    exit_time   = models.TimeField(null=True, blank=True)
    trade_type  = models.CharField(max_length=12, choices=TradeType.choices)
    status      = models.CharField(
        max_length=10, choices=TradeStatus.choices, default=TradeStatus.OPEN,
    )

    # Computed — do not set directly; use save()
    pnl         = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pnl_percent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Greeks at entry
    delta_entry = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    theta_entry = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    vega_entry  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    iv_entry    = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text='Implied Volatility at entry (decimal, e.g. 0.25 = 25%)',
    )

    # Risk management
    planned_stop_loss     = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    planned_take_profit_1 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    planned_take_profit_2 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    planned_take_profit_3 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    risk_reward_ratio     = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Tagging
    strategy_tags = models.JSONField(default=list, help_text='e.g. ["momentum", "VWAP reclaim"]')
    setup_quality = models.IntegerField(
        null=True, blank=True,
        help_text='1 (poor) – 5 (excellent) self-rating at entry',
    )
    trade_notes   = models.TextField(blank=True, help_text='Pre-trade rationale')
    exit_notes    = models.TextField(blank=True, help_text='Post-exit commentary')
    ta_screenshot = models.ImageField(
        upload_to='trade_ta/',
        null=True,
        blank=True,
        help_text='Optional technical analysis screenshot for this trade',
    )

    # Import tracking
    ibkr_trade_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True,
        help_text='IBKR TradeID for deduplication on CSV import',
    )
    imported      = models.BooleanField(default=False)

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-trade_date', '-entry_time']

    def __str__(self):
        return (
            f'{self.symbol} {self.option_type} {self.strike} '
            f'exp:{self.expiry} qty:{self.quantity} [{self.status}]'
        )

    # ------------------------------------------------------------------
    # P&L + R:R auto-calculation
    # ------------------------------------------------------------------

    def _compute_pnl(self):
        """
        Long  (LONG_CALL/LONG_PUT): pnl = (exit_price - entry_price) * qty * 100
        Short (CSP/CC):             pnl = (entry_price - exit_price) * qty * 100
        Expired worthless — Long:   pnl = -entry_price * qty * 100
        Expired worthless — Short:  pnl =  entry_price * qty * 100
        """
        qty = Decimal(str(self.quantity))
        ep  = Decimal(str(self.entry_price))

        is_long  = self.trade_type in (TradeType.LONG_CALL, TradeType.LONG_PUT)
        is_short = self.trade_type in (TradeType.CSP, TradeType.CC)

        if self.status == TradeStatus.EXPIRED:
            if is_long:
                pnl = -ep * qty * _MULTIPLIER
            elif is_short:
                pnl = ep * qty * _MULTIPLIER
            else:
                return None, None
        elif self.exit_price is not None:
            xp = Decimal(str(self.exit_price))
            if is_long:
                pnl = (xp - ep) * qty * _MULTIPLIER
            elif is_short:
                pnl = (ep - xp) * qty * _MULTIPLIER
            else:
                return None, None
        else:
            return None, None

        cost_basis = ep * qty * _MULTIPLIER
        try:
            pnl_pct = (pnl / cost_basis * Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )
        except InvalidOperation:
            pnl_pct = None

        return pnl.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), pnl_pct

    def _compute_rr(self):
        """R:R = reward / risk for long options.
        Risk  = (entry - stop_loss) * qty * 100  when stop_loss is set.
        Risk  = entry * qty * 100                 (full premium) when no stop.
        Reward= (tp1  - entry)     * qty * 100
        """
        if not (self.planned_take_profit_1 and self.entry_price and self.quantity):
            return None
        if self.trade_type not in (TradeType.LONG_CALL, TradeType.LONG_PUT):
            return None
        try:
            ep  = Decimal(str(self.entry_price))
            tp1 = Decimal(str(self.planned_take_profit_1))
            qty = Decimal(str(self.quantity))
            reward = (tp1 - ep) * qty * _MULTIPLIER
            if self.planned_stop_loss:
                sl = Decimal(str(self.planned_stop_loss))
                risk = (ep - sl) * qty * _MULTIPLIER
            else:
                risk = ep * qty * _MULTIPLIER
            if risk <= 0:
                return None
            return (reward / risk).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ZeroDivisionError):
            return None

    def save(self, *args, **kwargs):
        # Auto-link to the session for trade_date if not explicitly assigned.
        if not self.session_id and self.trade_date:
            session, _ = TradingSession.objects.get_or_create(date=self.trade_date)
            self.session = session
        self.pnl, self.pnl_percent = self._compute_pnl()
        self.risk_reward_ratio = self._compute_rr()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# DailyRoutine
# ---------------------------------------------------------------------------

class DailyRoutine(models.Model):
    session            = models.OneToOneField(
        TradingSession, on_delete=models.CASCADE, related_name='daily_routine',
    )
    checklist_template = models.ForeignKey(
        PreTradeChecklist, on_delete=models.SET_NULL, null=True, blank=True,
    )
    completed_items    = models.JSONField(default=dict, help_text='{item_id: bool}')
    completed_at       = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'DailyRoutine for {self.session.date}'

    @property
    def completion_percent(self):
        if not self.checklist_template or not self.checklist_template.items:
            return 0
        total = len(self.checklist_template.items)
        if total == 0:
            return 0
        done = sum(1 for v in self.completed_items.values() if v)
        return round(done / total * 100)


# ---------------------------------------------------------------------------
# JournalEntry
# ---------------------------------------------------------------------------

class JournalEntry(models.Model):
    title      = models.CharField(max_length=200)
    content    = models.TextField(help_text='Markdown supported')
    entry_type = models.CharField(
        max_length=15, choices=EntryType.choices, default=EntryType.OBSERVATION,
    )
    tags       = models.JSONField(default=list)
    trade      = models.ForeignKey(
        Trade, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal_entries',
    )
    session    = models.ForeignKey(
        TradingSession, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Journal entries'

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# PerformanceGoal
# ---------------------------------------------------------------------------

class PerformanceGoal(models.Model):
    title         = models.CharField(max_length=200)
    description   = models.TextField(blank=True)
    metric        = models.CharField(max_length=20, choices=GoalMetric.choices, null=True, blank=True)
    target_value  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    period        = models.CharField(max_length=12, choices=GoalPeriod.choices)
    start_date    = models.DateField()
    end_date      = models.DateField(null=True, blank=True)
    status        = models.CharField(
        max_length=10, choices=GoalStatus.choices, default=GoalStatus.ACTIVE,
    )

    class Meta:
        ordering = ['end_date', 'status']

    def __str__(self):
        return f'{self.title} ({self.period})'

    @property
    def progress_percent(self):
        if self.target_value in (None, 0) or self.current_value is None:
            return 0
        pct = float(self.current_value) / float(self.target_value) * 100
        return min(round(pct, 1), 100.0)

    @property
    def metric_display(self):
        if not self.metric:
            return 'Process Goal'
        return self.get_metric_display()

    @property
    def period_display(self):
        return self.get_period_display()

    @property
    def is_quantitative(self):
        return bool(self.metric and self.target_value is not None)

    @property
    def is_met(self):
        if self.status == GoalStatus.ACHIEVED:
            return True
        if not self.is_quantitative or self.current_value is None:
            return False
        return self.current_value >= self.target_value
