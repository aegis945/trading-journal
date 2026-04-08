"""
journal/views.py

Phase 1: All views are wired and return rendered templates.
Dashboard and session views have real logic; others are stubs
that will be filled out in Phase 2+.
"""

import csv
import calendar as cal_module
import datetime
import io
import json
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from .models import (
    TradingSession, Trade, PreTradeChecklist, DailyRoutine,
    JournalEntry, PerformanceGoal,
    RuleReview, TradeStatus, TradeType, OptionType, MarketBias,
    is_market_closed_day, market_closed_label, market_holiday_name, previous_market_day,
)
from .forms import TradeForm, TradingSessionForm

# ============================================================
# Dashboard
# ============================================================

def dashboard(request):
    today = timezone.localdate()
    is_market_closed = is_market_closed_day(today)

    session = None
    daily_routine = None
    session_trades = Trade.objects.none()
    today_pnl = Decimal('0')

    if not is_market_closed:
        # Auto-create today's session if it doesn't exist
        session, created = TradingSession.objects.get_or_create(date=today)

        # Get or create a daily routine linked to the active checklist template
        try:
            daily_routine = session.daily_routine
        except DailyRoutine.DoesNotExist:
            active_template = PreTradeChecklist.objects.filter(is_active=True).first()
            daily_routine = DailyRoutine.objects.create(
                session=session,
                checklist_template=active_template,
            )

        # Current session trades
        session_trades = Trade.objects.filter(session=session)

        # Today's P&L
        today_pnl = Trade.objects.filter(
            session=session,
            status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED],
        ).aggregate(total=Sum('pnl'))['total'] or Decimal('0')

    # 30-day stats
    thirty_days_ago = today - datetime.timedelta(days=30)
    recent_closed = Trade.objects.filter(
        trade_date__gte=thirty_days_ago,
        status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED],
    )
    total_recent = recent_closed.count()
    win_count_30d = recent_closed.filter(pnl__gt=0).count()
    win_rate_30d  = round(win_count_30d / total_recent * 100, 1) if total_recent else 0

    avg_rr = recent_closed.filter(
        risk_reward_ratio__isnull=False
    ).aggregate(avg=Avg('risk_reward_ratio'))['avg']
    avg_rr = round(float(avg_rr), 2) if avg_rr else None

    seven_days_ago = today - datetime.timedelta(days=6)
    weekly_reviewed = Trade.objects.filter(
        trade_date__gte=seven_days_ago,
        status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED],
        rule_review__in=[RuleReview.FOLLOWED, RuleReview.BROKE],
    )
    weekly_reviewed_count = weekly_reviewed.count()
    weekly_followed_count = weekly_reviewed.filter(rule_review=RuleReview.FOLLOWED).count()
    weekly_rule_follow_rate = round(weekly_followed_count / weekly_reviewed_count * 100, 1) if weekly_reviewed_count else None

    rule_break_counter = {}
    for trade in recent_closed.filter(rule_review=RuleReview.BROKE).values('rule_break_tags'):
        tags = trade['rule_break_tags'] or ['Unspecified']
        for tag in tags:
            rule_break_counter[tag] = rule_break_counter.get(tag, 0) + 1
    top_rule_break_tags = []
    top_rule_break_count = 0
    if rule_break_counter:
        top_rule_break_count = max(rule_break_counter.values())
        top_rule_break_tags = sorted([
            tag for tag, count in rule_break_counter.items()
            if count == top_rule_break_count
        ])

    # Streak: query last 50 closed trades ordered by date desc
    streak_trades = list(
        Trade.objects.filter(
            status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED],
            pnl__isnull=False,
        ).order_by('-trade_date', '-entry_time').values('pnl')[:50]
    )
    streak, streak_type = _compute_current_streak(streak_trades)

    # Best / worst strategy tags by avg P&L (30d)
    tag_stats = _compute_tag_stats(recent_closed)

    # Recent journal entries
    recent_journal = JournalEntry.objects.select_related('trade', 'session').order_by('-created_at')[:5]

    app_prompts = []
    if session and not session.is_pre_market_complete:
        app_prompts.append({
            'level': 'info',
            'text': "Today's session plan is still blank.",
            'detail': 'Set your bias, mindset, and market context before the session gets going.',
            'url': reverse('session_detail', args=[session.date.isoformat()]),
            'label': 'Fill it out',
        })
    if session and session_trades.exists() and not session.has_post_session_reflection:
        app_prompts.append({
            'level': 'warning',
            'text': 'This session has trades but no reflection.',
            'detail': 'Capture what you learned while the context is still fresh.',
            'url': reverse('session_detail', args=[session.date.isoformat()]),
            'label': 'Add reflection',
        })

    context = {
        'session': session,
        'session_date': today,
        'daily_routine': daily_routine,
        'session_trades': session_trades,
        'today_pnl': today_pnl,
        'win_rate_30d': win_rate_30d,
        'avg_rr': avg_rr,
        'weekly_rule_follow_rate': weekly_rule_follow_rate,
        'weekly_reviewed_count': weekly_reviewed_count,
        'top_rule_break_tags': top_rule_break_tags,
        'top_rule_break_count': top_rule_break_count,
        'streak': streak,
        'streak_type': streak_type,
        'tag_stats': tag_stats,
        'recent_journal': recent_journal,
        'app_prompts': app_prompts,
        'trade_form': TradeForm(initial={'trade_date': previous_market_day(today), 'expiry': previous_market_day(today), 'symbol': 'SPX'}),
        'is_market_closed': is_market_closed,
        'market_closed_label': market_closed_label(today),
        'market_holiday_name': market_holiday_name(today),
        'now': timezone.now(),
    }
    return render(request, 'dashboard/index.html', context)


def _compute_current_streak(trades):
    """Returns (streak_count, 'WIN'|'LOSS'|None) from newest-first list."""
    if not trades:
        return 0, None
    first_win = trades[0]['pnl'] > 0
    streak_type = 'WIN' if first_win else 'LOSS'
    count = 0
    for t in trades:
        is_win = t['pnl'] > 0
        if is_win == first_win:
            count += 1
        else:
            break
    return count, streak_type


def _compute_tag_stats(qs):
    """
    Returns {'best_tag': str, 'worst_tag': str} from a queryset of closed trades.
    Iterates Python-side (tags stored as JSONField array).
    """
    tag_pnl: dict[str, list] = {}
    for trade in qs.filter(pnl__isnull=False).values('strategy_tags', 'pnl'):
        for tag in (trade['strategy_tags'] or []):
            tag_pnl.setdefault(tag, []).append(float(trade['pnl']))
    if not tag_pnl:
        return {'best_tag': None, 'worst_tag': None}
    avg_by_tag = {tag: sum(v) / len(v) for tag, v in tag_pnl.items()}
    ranked_tags = sorted(avg_by_tag.items(), key=lambda item: item[1], reverse=True)
    best = ranked_tags[0][0]
    worst = None
    if len(ranked_tags) > 1 and ranked_tags[0][1] != ranked_tags[-1][1]:
        worst = ranked_tags[-1][0]
    return {'best_tag': best, 'worst_tag': worst, 'avg_by_tag': avg_by_tag}


# ============================================================
# Trades
# ============================================================

def trade_list(request):
    qs = Trade.objects.select_related('session').all()

    # Filtering
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    opt_type  = request.GET.get('option_type')
    ttype     = request.GET.get('trade_type')
    status    = request.GET.get('status')
    tag       = request.GET.get('tag')
    rule_review = request.GET.get('rule_review')

    if date_from:
        qs = qs.filter(trade_date__gte=date_from)
    if date_to:
        qs = qs.filter(trade_date__lte=date_to)
    if opt_type:
        qs = qs.filter(option_type=opt_type)
    if ttype:
        qs = qs.filter(trade_type=ttype)
    if status:
        qs = qs.filter(status=status)
    if rule_review == 'UNREVIEWED':
        qs = qs.filter(Q(rule_review__isnull=True) | Q(rule_review=''))
    elif rule_review:
        qs = qs.filter(rule_review=rule_review)
    if tag:
        tag = tag.strip().lower()
        # SQLite JSONField doesn't support __contains for array membership;
        # filter in Python after fetching the queryset.
        qs = [
            trade for trade in qs
            if any(tag in strategy_tag.lower() for strategy_tag in (trade.strategy_tags or []))
        ]

    return render(request, 'journal/trade_list.html', {
        'trades': qs,
        'option_type_choices': OptionType.choices,
        'trade_type_choices': TradeType.choices,
        'status_choices': TradeStatus.choices,
        'rule_review_choices': [('FOLLOWED', 'Followed rules'), ('BROKE', 'Rule break'), ('UNREVIEWED', 'Not reviewed')],
        'filters': request.GET,
    })


def _ibkr_connected():
    try:
        from ibkr.client import ib_client
        return ib_client.is_connected()
    except Exception:
        return False


def trade_add(request):
    if request.method == 'POST':
        form = TradeForm(request.POST, request.FILES)
        if form.is_valid():
            trade = form.save()
            messages.success(request, f'Trade saved: {trade}')
            return redirect('trade_detail', pk=trade.pk)
    else:
        today = timezone.localdate()
        default_trade_date = previous_market_day(today)
        form = TradeForm(initial={'trade_date': default_trade_date, 'expiry': default_trade_date, 'symbol': 'SPX'})
    return render(request, 'journal/trade_form.html', {'form': form, 'title': 'Add Trade', 'ibkr_connected': _ibkr_connected()})


def trade_quick_add(request):
    """Returns HTMX modal partial for the quick-add drawer from the topbar."""
    today = timezone.localdate()
    default_trade_date = previous_market_day(today)
    form = TradeForm(initial={'trade_date': default_trade_date, 'expiry': default_trade_date, 'symbol': 'SPX'})
    if request.method == 'POST':
        form = TradeForm(request.POST, request.FILES)
        if form.is_valid():
            trade = form.save()
            # Return empty modal + trigger dashboard refresh
            response = HttpResponse('<div id="modal-container"></div>')
            response['HX-Trigger'] = 'dashboardRefresh'
            return response
    return render(request, 'components/trade_quick_add.html', {'form': form})


def trade_detail(request, pk):
    trade = get_object_or_404(Trade.objects.select_related('session'), pk=pk)
    journal_entries = trade.journal_entries.all()
    return render(request, 'journal/trade_detail.html', {
        'trade': trade,
        'journal_entries': journal_entries,
    })


def trade_edit(request, pk):
    trade = get_object_or_404(Trade, pk=pk)
    if request.method == 'POST':
        form = TradeForm(request.POST, request.FILES, instance=trade)
        if form.is_valid():
            form.save()
            messages.success(request, 'Trade updated.')
            return redirect('trade_detail', pk=trade.pk)
    else:
        form = TradeForm(instance=trade)
    return render(request, 'journal/trade_form.html', {'form': form, 'trade': trade, 'title': 'Edit Trade', 'ibkr_connected': _ibkr_connected()})


@require_POST
def trade_screenshot_delete(request, pk):
    trade = get_object_or_404(Trade, pk=pk)

    if trade.ta_screenshot:
        trade.ta_screenshot.delete(save=False)
        trade.ta_screenshot = None
        trade.save()
        messages.success(request, 'Screenshot deleted. You can upload a new one now.')
    else:
        messages.info(request, 'This trade does not have a saved screenshot.')

    return redirect('trade_edit', pk=trade.pk)


def trade_delete(request, pk):
    trade = get_object_or_404(Trade, pk=pk)
    if request.method == 'POST':
        trade.delete()
        messages.success(request, 'Trade deleted.')
        return redirect('trade_list')
    return redirect('trade_detail', pk=pk)


def trade_export(request):
    """Stream all (filtered) trades as CSV."""
    qs = Trade.objects.select_related('session').all()
    # Apply same filters as trade_list
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(trade_date__gte=date_from)
    if date_to:
        qs = qs.filter(trade_date__lte=date_to)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="trades_export.csv"'
    writer = csv.writer(response)
    header = [
        'trade_date', 'symbol', 'option_type', 'strike', 'expiry',
        'quantity', 'entry_price', 'exit_price', 'entry_time', 'exit_time',
        'trade_type', 'status', 'pnl', 'pnl_percent', 'risk_reward_ratio',
        'delta_entry', 'theta_entry', 'vega_entry', 'iv_entry',
        'planned_stop_loss', 'planned_take_profit_1', 'planned_take_profit_2',
        'planned_take_profit_3', 'strategy_tags', 'setup_quality', 'trade_notes', 'exit_notes',
    ]
    writer.writerow(header)
    for t in qs:
        writer.writerow([
            t.trade_date, t.symbol, t.option_type, t.strike, t.expiry,
            t.quantity, t.entry_price, t.exit_price, t.entry_time, t.exit_time,
            t.trade_type, t.status, t.pnl, t.pnl_percent, t.risk_reward_ratio,
            t.delta_entry, t.theta_entry, t.vega_entry, t.iv_entry,
            t.planned_stop_loss, t.planned_take_profit_1, t.planned_take_profit_2,
            t.planned_take_profit_3, json.dumps(t.strategy_tags), t.setup_quality,
            t.trade_notes, t.exit_notes,
        ])
    return response


# ============================================================
# Sessions
# ============================================================

def session_list(request):
    sessions = TradingSession.objects.prefetch_related('trades').order_by('-date')
    return render(request, 'journal/session_list.html', {'sessions': sessions})


def session_detail(request, date):
    try:
        session_date = datetime.date.fromisoformat(date)
    except ValueError:
        return redirect('session_list')

    if is_market_closed_day(session_date):
        return render(request, 'journal/session_detail.html', {
            'session': TradingSession(date=session_date),
            'daily_routine': None,
            'trades': Trade.objects.none(),
            'total_pnl': Decimal('0'),
            'form': None,
            'market_closed': True,
            'market_closed_label': market_closed_label(session_date),
            'market_holiday_name': market_holiday_name(session_date),
        })

    session = TradingSession.objects.filter(date=session_date).first()
    is_new_session = session is None

    if is_new_session:
        session = TradingSession(date=session_date)
        daily_routine = None
        trades = Trade.objects.none()
        total_pnl = Decimal('0')
    else:
        try:
            daily_routine = session.daily_routine
        except DailyRoutine.DoesNotExist:
            active_template = PreTradeChecklist.objects.filter(is_active=True).first()
            daily_routine = DailyRoutine.objects.create(
                session=session,
                checklist_template=active_template,
            )

        trades = session.trades.all()
        total_pnl = session.total_pnl

    if request.method == 'POST':
        form = TradingSessionForm(request.POST, instance=session)
        if form.is_valid():
            session = form.save()
            if not hasattr(session, 'daily_routine'):
                active_template = PreTradeChecklist.objects.filter(is_active=True).first()
                daily_routine = DailyRoutine.objects.create(
                    session=session,
                    checklist_template=active_template,
                )
            messages.success(request, 'Session updated.')
            return redirect('session_detail', date=date)
    else:
        form = TradingSessionForm(instance=session)

    return render(request, 'journal/session_detail.html', {
        'session': session,
        'daily_routine': daily_routine,
        'trades': trades,
        'total_pnl': total_pnl,
        'form': form,
        'market_closed': False,
        'market_closed_label': '',
        'market_holiday_name': '',
    })


def session_edit(request, date):
    return redirect('session_detail', date=date)


@require_POST
def checklist_toggle(request, date, item_id):
    """HTMX: toggle a single checklist item and return updated partial."""
    try:
        session_date = datetime.date.fromisoformat(date)
    except ValueError:
        return HttpResponse(status=400)

    if is_market_closed_day(session_date):
        return HttpResponse(status=400)

    session = get_object_or_404(TradingSession, date=session_date)
    try:
        daily_routine = session.daily_routine
    except DailyRoutine.DoesNotExist:
        return HttpResponse(status=404)

    current = daily_routine.completed_items.get(item_id, False)
    daily_routine.completed_items[item_id] = not current

    # Mark completed_at if all items done
    if daily_routine.checklist_template:
        all_ids = {item['id'] for item in daily_routine.checklist_template.items}
        if all_ids and all(daily_routine.completed_items.get(i, False) for i in all_ids):
            daily_routine.completed_at = timezone.now()
        else:
            daily_routine.completed_at = None

    daily_routine.save()

    return render(request, 'components/checklist_item.html', {
        'item': next(
            (i for i in (daily_routine.checklist_template.items if daily_routine.checklist_template else [])
             if i['id'] == item_id),
            {'id': item_id, 'label': item_id, 'category': ''},
        ),
        'checked': daily_routine.completed_items.get(item_id, False),
        'session': session,
    })


# ============================================================
# Calendar
# ============================================================

def calendar_view(request):
    today = timezone.localdate()
    year  = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Clamp year/month
    if month < 1:   month, year = 12, year - 1
    if month > 12:  month, year = 1, year + 1

    # Month grid
    first_weekday, days_in_month = cal_module.monthrange(year, month)
    # Pad start to Monday=0 grid
    grid_days_before = first_weekday  # Monday-based

    # Aggregate session data for this month
    sessions = {
        s.date: s
        for s in TradingSession.objects.filter(
            date__year=year, date__month=month
        ).prefetch_related('trades')
    }

    # Previous / next month links
    prev_month = datetime.date(year, month, 1) - datetime.timedelta(days=1)
    next_month = datetime.date(year, month, days_in_month) + datetime.timedelta(days=1)

    weeks = _build_calendar_grid(year, month, days_in_month, grid_days_before, sessions, today)

    # Monthly totals
    month_pnl = sum(
        s.total_pnl for s in sessions.values()
    )

    return render(request, 'calendar/index.html', {
        'year': year,
        'month': month,
        'month_name': cal_module.month_name[month],
        'weeks': weeks,
        'month_pnl': month_pnl,
        'prev_year': prev_month.year, 'prev_month': prev_month.month,
        'next_year': next_month.year, 'next_month': next_month.month,
        'today': today,
    })


def _build_calendar_grid(year, month, days_in_month, pad_before, sessions, today):
    """Returns list of week-rows, each containing day-cell dicts."""
    days = []
    # Leading empty cells
    for _ in range(pad_before):
        days.append(None)
    for day_num in range(1, days_in_month + 1):
        d = datetime.date(year, month, day_num)
        session = sessions.get(d)
        pnl = session.total_pnl if session else None
        is_closed = is_market_closed_day(d)
        days.append({
            'date': d,
            'session': session,
            'pnl': pnl,
            'trade_count': session.trade_count if session else 0,
            'psych_state': session.psychological_state if session else None,
            'is_today': d == today,
            'is_closed': is_closed,
            'closed_label': market_holiday_name(d) or market_closed_label(d),
        })
    # Chunk into weeks of 7
    weeks = []
    for i in range(0, len(days), 7):
        weeks.append(days[i:i+7])
    # Pad last week
    if weeks and len(weeks[-1]) < 7:
        weeks[-1].extend([None] * (7 - len(weeks[-1])))
    return weeks


# ============================================================
# Journal Entries
# ============================================================

def journal_list(request):
    qs = JournalEntry.objects.select_related('trade', 'session').all()
    entry_type = request.GET.get('entry_type')
    tag        = request.GET.get('tag')
    q          = request.GET.get('q')
    if entry_type:
        qs = qs.filter(entry_type=entry_type)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
    if tag:
        # SQLite JSONField doesn't support __contains for array membership;
        # filter in Python after evaluating the queryset.
        qs = [e for e in qs if tag.lower() in [x.lower() for x in (e.tags or [])]]
    return render(request, 'journal/journal_list.html', {
        'entries': qs,
        'entry_type_choices': JournalEntry._meta.get_field('entry_type').choices,
        'filters': request.GET,
    })


def journal_new(request):
    from .forms import JournalEntryForm
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        if form.is_valid():
            entry = form.save()
            return redirect('journal_detail', pk=entry.pk)
    else:
        form = JournalEntryForm()
    return render(request, 'journal/journal_form.html', {'form': form, 'title': 'New Entry'})


def journal_detail(request, pk):
    entry = get_object_or_404(JournalEntry, pk=pk)
    return render(request, 'journal/journal_detail.html', {'entry': entry})


def journal_edit(request, pk):
    from .forms import JournalEntryForm
    entry = get_object_or_404(JournalEntry, pk=pk)
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            return redirect('journal_detail', pk=pk)
    else:
        form = JournalEntryForm(instance=entry)
    return render(request, 'journal/journal_form.html', {'form': form, 'entry': entry, 'title': 'Edit Entry'})


def journal_delete(request, pk):
    entry = get_object_or_404(JournalEntry, pk=pk)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Entry deleted.')
        return redirect('journal_list')
    return render(request, 'journal/journal_confirm_delete.html', {'entry': entry})


# ============================================================
# Performance Goals
# ============================================================

def goals_list(request):
    goals = PerformanceGoal.objects.all()
    return render(request, 'goals/index.html', {'goals': goals})


def goal_new(request):
    from .forms import PerformanceGoalForm
    if request.method == 'POST':
        form = PerformanceGoalForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('goals')
    else:
        form = PerformanceGoalForm()
    return render(request, 'goals/goal_form.html', {'form': form, 'title': 'New Goal'})


def goal_edit(request, pk):
    from .forms import PerformanceGoalForm
    goal = get_object_or_404(PerformanceGoal, pk=pk)
    if request.method == 'POST':
        form = PerformanceGoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            return redirect('goals')
    else:
        form = PerformanceGoalForm(instance=goal)
    return render(request, 'goals/goal_form.html', {'form': form, 'goal': goal, 'title': 'Edit Goal'})


def goal_delete(request, pk):
    goal = get_object_or_404(PerformanceGoal, pk=pk)
    if request.method == 'POST':
        goal.delete()
        return redirect('goals')
    return render(request, 'goals/goal_confirm_delete.html', {'goal': goal})


# ============================================================
# Settings / Checklist templates
# ============================================================

def settings_index(request):
    from .forms import AppPreferencesForm, RuleBreakSettingsForm
    from .models import get_app_preferences
    from urllib.error import URLError

    preferences = get_app_preferences()
    rate_fetch_error = None
    currency_form = AppPreferencesForm(instance=preferences)
    rule_break_form = RuleBreakSettingsForm(instance=preferences)
    if request.method == 'POST':
        if 'save_rule_break_tags' in request.POST:
            rule_break_form = RuleBreakSettingsForm(request.POST, instance=preferences)
            if rule_break_form.is_valid():
                rule_break_form.save()
                messages.success(request, 'Rule-break presets updated.')
                return redirect('settings_index')
        else:
            currency_form = AppPreferencesForm(request.POST, instance=preferences)
            if currency_form.is_valid():
                preferences = currency_form.save()
                if preferences.display_currency == 'EUR':
                    try:
                        preferences.refresh_exchange_rate_if_needed(force=True)
                    except (URLError, ValueError):
                        rate_fetch_error = (
                            'Could not refresh the live USD to EUR rate. '
                            'Using the last saved rate instead.'
                        )
                if rate_fetch_error:
                    messages.warning(request, rate_fetch_error)
                else:
                    messages.success(request, 'Display preferences updated.')
                return redirect('settings_index')

    if preferences.display_currency == 'EUR':
        try:
            preferences.refresh_exchange_rate_if_needed()
        except (URLError, ValueError):
            rate_fetch_error = 'Live USD to EUR rate is temporarily unavailable.'

    return render(request, 'settings/index.html', {
        'preferences_form': currency_form,
        'rule_break_form': rule_break_form,
        'preferences': preferences,
        'rate_fetch_error': rate_fetch_error,
    })


def settings_checklist(request):
    templates = PreTradeChecklist.objects.all()
    return render(request, 'settings/checklist.html', {'templates': templates})


def checklist_template_new(request):
    from .forms import PreTradeChecklistForm
    if request.method == 'POST':
        form = PreTradeChecklistForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('settings_checklist')
    else:
        form = PreTradeChecklistForm()
    return render(request, 'settings/checklist_form.html', {'form': form, 'title': 'New Checklist Template'})


def checklist_template_edit(request, pk):
    from .forms import PreTradeChecklistForm
    template = get_object_or_404(PreTradeChecklist, pk=pk)
    if request.method == 'POST':
        form = PreTradeChecklistForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            return redirect('settings_checklist')
    else:
        form = PreTradeChecklistForm(instance=template)
    return render(request, 'settings/checklist_form.html', {'form': form, 'template': template, 'title': 'Edit Checklist'})


@require_POST
def checklist_template_delete(request, pk):
    template = get_object_or_404(PreTradeChecklist, pk=pk)
    template.delete()
    return redirect('settings_checklist')


@require_POST
def checklist_template_activate(request, pk):
    template = get_object_or_404(PreTradeChecklist, pk=pk)
    template.is_active = True
    template.save()  # save() enforces single-active invariant
    return redirect('settings_checklist')


# ============================================================
# CSV Import
# ============================================================

def import_upload(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        from ibkr.parser import IBKRCSVParser
        import os
        from django.conf import settings as django_settings

        upload_dir = django_settings.MEDIA_ROOT / 'imports'
        upload_dir.mkdir(parents=True, exist_ok=True)

        csv_file = request.FILES['csv_file']
        # Sanitise filename
        safe_name = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}_{csv_file.name.replace(' ', '_')}"
        dest = upload_dir / safe_name
        with open(dest, 'wb') as f:
            for chunk in csv_file.chunks():
                f.write(chunk)

        # Quick parse to count rows
        parser = IBKRCSVParser(dest)
        rows = parser.parse()
        request.session['import_parsed_count'] = len(rows)

        return redirect('import_preview', filename=safe_name)

    return render(request, 'journal/import_upload.html', {})


def import_preview(request, filename):
    from ibkr.parser import IBKRCSVParser
    from django.conf import settings as django_settings

    dest = django_settings.MEDIA_ROOT / 'imports' / filename
    if not dest.exists():
        messages.error(request, 'Import file not found.')
        return redirect('import_upload')

    parser = IBKRCSVParser(dest)
    rows = parser.parse()
    return render(request, 'journal/import_preview.html', {
        'rows': rows[:200],  # cap preview at 200 rows
        'total': len(rows),
        'filename': filename,
    })


@require_POST
def import_confirm(request, filename):
    from ibkr.parser import IBKRCSVParser
    from django.conf import settings as django_settings

    dest = django_settings.MEDIA_ROOT / 'imports' / filename
    if not dest.exists():
        messages.error(request, 'Import file not found.')
        return redirect('import_upload')

    parser = IBKRCSVParser(dest)
    rows = parser.parse()

    new_count = skipped_count = error_count = 0
    for row in rows:
        ibkr_id = row.get('ibkr_trade_id')
        if ibkr_id and Trade.objects.filter(ibkr_trade_id=ibkr_id).exists():
            skipped_count += 1
            continue
        if is_market_closed_day(row['trade_date']):
            error_count += 1
            continue
        try:
            # Attach to a session by trade_date — get_or_create
            session, _ = TradingSession.objects.get_or_create(date=row['trade_date'])
            row['session'] = session
            row.pop('ibkr_trade_id', None)
            ibkr_id_val = ibkr_id  # already popped from row
            trade = Trade(**row, ibkr_trade_id=ibkr_id_val, imported=True)
            trade.save()
            new_count += 1
        except Exception:
            error_count += 1

    messages.success(
        request,
        f'Import complete: {new_count} new, {skipped_count} duplicates skipped, {error_count} errors.',
    )
    return redirect('trade_list')
