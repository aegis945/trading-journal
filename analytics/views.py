"""
analytics/views.py

Phase 1: stub views returning JSON endpoints.
Charts are wired to Chart.js on the analytics page.
Full aggregation logic implemented here — Phase 4.
"""

import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Sum, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from journal.models import EntryType, RuleReview, Trade, TradingSession, TradeStatus, JournalEntry


def analytics_index(request):
    periods = [('7d', '7'), ('30d', '30'), ('90d', '90'), ('All', '')]
    return render(request, 'analytics/index.html', {'periods': periods})


def performance_review(request):
    week_start = _resolve_review_week_start(request)
    week_end = week_start + datetime.timedelta(days=6)

    all_week_trades = Trade.objects.filter(trade_date__range=(week_start, week_end)).select_related('session')
    closed_week_trades = all_week_trades.filter(
        status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED],
        pnl__isnull=False,
    )
    sessions = TradingSession.objects.filter(date__range=(week_start, week_end)).prefetch_related('trades', 'journal_entries')
    journal_entries = JournalEntry.objects.filter(created_at__date__range=(week_start, week_end)).select_related('trade', 'session')

    total_trades = all_week_trades.count()
    closed_trade_count = closed_week_trades.count()
    wins = closed_week_trades.filter(pnl__gt=0).count()
    total_pnl = closed_week_trades.aggregate(total=Sum('pnl'))['total'] or Decimal('0')
    avg_rr = closed_week_trades.filter(risk_reward_ratio__isnull=False).aggregate(avg=Avg('risk_reward_ratio'))['avg']
    avg_rr = round(float(avg_rr), 2) if avg_rr is not None else None
    reviewed_trades = closed_week_trades.filter(rule_review__in=[RuleReview.FOLLOWED, RuleReview.BROKE])
    reviewed_count = reviewed_trades.count()
    followed_count = reviewed_trades.filter(rule_review=RuleReview.FOLLOWED).count()
    followed_rate = round(followed_count / reviewed_count * 100, 1) if reviewed_count else None

    best_trade = closed_week_trades.filter(pnl__gt=0).order_by('-pnl', '-trade_date', '-entry_time').first()
    worst_trade = closed_week_trades.filter(pnl__lt=0).order_by('pnl', '-trade_date', '-entry_time').first()

    rule_break_counter = defaultdict(int)
    strategy_counter = defaultdict(int)
    for trade in closed_week_trades:
        for tag in (trade.rule_break_tags or []):
            rule_break_counter[tag] += 1
        for tag in (trade.strategy_tags or []):
            strategy_counter[tag] += 1

    top_rule_breaks = _sorted_counter_items(rule_break_counter)
    top_strategy_tags = _sorted_counter_items(strategy_counter)

    session_rows = []
    for offset in range(5):
        day = week_start + datetime.timedelta(days=offset)
        session = next((item for item in sessions if item.date == day), None)
        day_trades = [trade for trade in all_week_trades if trade.trade_date == day]
        closed_day_trades = [trade for trade in day_trades if trade.status in [TradeStatus.CLOSED, TradeStatus.EXPIRED] and trade.pnl is not None]
        session_rows.append({
            'date': day,
            'session': session,
            'trade_count': len(day_trades),
            'closed_trade_count': len(closed_day_trades),
            'pnl': sum((trade.pnl for trade in closed_day_trades), Decimal('0')),
            'journal_count': journal_entries.filter(session=session).count() if session else 0,
        })

    session_prep_completed = sum(1 for session in sessions if session.is_pre_market_complete)
    session_reflections_completed = sum(1 for session in sessions if session.has_post_session_reflection)
    linked_trade_journal_count = journal_entries.filter(trade__isnull=False).count()

    journal_type_counts = []
    for entry_type, label in EntryType.choices:
        count = journal_entries.filter(entry_type=entry_type).count()
        if count:
            journal_type_counts.append({'label': label, 'count': count})

    context = {
        'week_start': week_start,
        'week_end': week_end,
        'previous_week': week_start - datetime.timedelta(days=7),
        'next_week': week_start + datetime.timedelta(days=7),
        'stats': {
            'total_pnl': total_pnl,
            'win_rate': round(wins / closed_trade_count * 100, 1) if closed_trade_count else 0,
            'total_trades': total_trades,
            'closed_trades': closed_trade_count,
            'avg_rr': avg_rr,
            'rule_follow_rate': followed_rate,
            'reviewed_trade_count': reviewed_count,
            'journal_entries': journal_entries.count(),
            'session_prep_completed': session_prep_completed,
            'session_reflections_completed': session_reflections_completed,
        },
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'top_rule_breaks': top_rule_breaks,
        'top_strategy_tags': top_strategy_tags,
        'session_rows': session_rows,
        'sessions': sessions,
        'journal_entries': journal_entries.order_by('-created_at'),
        'journal_type_counts': journal_type_counts,
        'linked_trade_journal_count': linked_trade_journal_count,
    }
    return render(request, 'analytics/review.html', context)


def _sorted_counter_items(counter):
    return [
        {'label': label, 'count': count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _latest_review_anchor_date():
    candidate_dates = []

    latest_trade = Trade.objects.order_by('-trade_date').values_list('trade_date', flat=True).first()
    if latest_trade:
        candidate_dates.append(latest_trade)

    latest_session = TradingSession.objects.order_by('-date').values_list('date', flat=True).first()
    if latest_session:
        candidate_dates.append(latest_session)

    latest_journal = JournalEntry.objects.order_by('-created_at').first()
    if latest_journal:
        candidate_dates.append(timezone.localtime(latest_journal.created_at).date())

    return max(candidate_dates) if candidate_dates else timezone.localdate()


def _resolve_review_week_start(request):
    raw_week = request.GET.get('week')
    if raw_week:
        try:
            selected = datetime.date.fromisoformat(raw_week)
        except ValueError:
            selected = _latest_review_anchor_date()
    else:
        selected = _latest_review_anchor_date()
    return selected - datetime.timedelta(days=selected.weekday())


def _closed_qs(request):
    """Base queryset for closed/expired trades, optional ?days= filter."""
    days = request.GET.get('days')
    qs   = Trade.objects.filter(status__in=[TradeStatus.CLOSED, TradeStatus.EXPIRED], pnl__isnull=False)
    if days:
        cutoff = timezone.localdate() - datetime.timedelta(days=int(days))
        qs = qs.filter(trade_date__gte=cutoff)
    return qs


def data_win_rate_by_tag(request):
    qs = _closed_qs(request)
    tag_data: dict[str, dict] = defaultdict(lambda: {'wins': 0, 'total': 0})
    for row in qs.values('strategy_tags', 'pnl'):
        for tag in (row['strategy_tags'] or []):
            tag_data[tag]['total'] += 1
            if row['pnl'] > 0:
                tag_data[tag]['wins'] += 1
    labels, win_rates = [], []
    for tag, d in sorted(tag_data.items(), key=lambda x: -x[1]['total']):
        labels.append(tag)
        win_rates.append(round(d['wins'] / d['total'] * 100, 1) if d['total'] else 0)
    return JsonResponse({'labels': labels, 'win_rates': win_rates})


def data_pnl_by_weekday(request):
    """Avg P&L and win rate grouped by day of week (Mon–Fri)."""
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    qs = _closed_qs(request).values('trade_date', 'pnl')
    slots: dict[int, list] = {i: [] for i in range(5)}
    for row in qs:
        dow = row['trade_date'].weekday()  # 0=Mon … 4=Fri
        if dow < 5:
            slots[dow].append(float(row['pnl']))
    labels, avg_pnl, win_rates, counts = [], [], [], []
    for i in range(5):
        vals = slots[i]
        labels.append(DAYS[i])
        avg_pnl.append(round(sum(vals) / len(vals), 2) if vals else 0)
        win_rates.append(round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1) if vals else 0)
        counts.append(len(vals))
    return JsonResponse({'labels': labels, 'avg_pnl': avg_pnl, 'win_rates': win_rates, 'counts': counts})


def data_pnl_by_time(request):
    """P&L bucketed by 30-min intervals (ET), 9:30–16:00."""
    qs    = _closed_qs(request).values('entry_time', 'pnl')
    slots = defaultdict(list)
    for row in qs:
        t = row['entry_time']
        # bucket: floor to 30 min
        minute_bucket = (t.minute // 30) * 30
        label = f'{t.hour:02d}:{minute_bucket:02d}'
        slots[label].append(float(row['pnl']))
    labels    = sorted(slots.keys())
    avg_pnl   = [round(sum(slots[l]) / len(slots[l]), 2) for l in labels]
    return JsonResponse({'labels': labels, 'avg_pnl': avg_pnl})


def data_psych_vs_outcome(request):
    result = []
    for state in range(1, 6):
        qs = _closed_qs(request).filter(session__psychological_state=state)
        agg = qs.aggregate(avg_pnl=Avg('pnl'), count=Count('id'))
        wins = qs.filter(pnl__gt=0).count()
        total = agg['count'] or 0
        result.append({
            'state': state,
            'avg_pnl': round(float(agg['avg_pnl'] or 0), 2),
            'win_rate': round(wins / total * 100, 1) if total else 0,
            'count': total,
        })
    return JsonResponse({'data': result})


def data_delta_vs_pnl(request):
    rows = _closed_qs(request).filter(
        delta_entry__isnull=False
    ).values('delta_entry', 'pnl')[:500]
    points = [{'x': float(r['delta_entry']), 'y': float(r['pnl'])} for r in rows]
    return JsonResponse({'points': points})


def data_streak(request):
    trades = list(
        _closed_qs(request).order_by('trade_date', 'entry_time').values('trade_date', 'pnl')
    )
    streaks = []
    if not trades:
        return JsonResponse({'streaks': []})
    current_type = 'WIN' if trades[0]['pnl'] > 0 else 'LOSS'
    count = 0
    start = str(trades[0]['trade_date'])
    for t in trades:
        is_win = t['pnl'] > 0
        t_type = 'WIN' if is_win else 'LOSS'
        if t_type == current_type:
            count += 1
        else:
            streaks.append({'type': current_type, 'count': count, 'start': start})
            current_type = t_type
            count = 1
            start = str(t['trade_date'])
    streaks.append({'type': current_type, 'count': count, 'start': start})
    return JsonResponse({'streaks': streaks})


def data_drawdown(request):
    trades = list(
        _closed_qs(request).order_by('trade_date', 'entry_time').values('trade_date', 'pnl')
    )
    labels, equity, drawdown = [], [], []
    peak = Decimal('0')
    cumulative = Decimal('0')
    for t in trades:
        cumulative += t['pnl']
        if cumulative > peak:
            peak = cumulative
        dd = float(cumulative - peak)
        labels.append(str(t['trade_date']))
        equity.append(float(cumulative))
        drawdown.append(dd)
    return JsonResponse({'labels': labels, 'equity': equity, 'drawdown': drawdown})


def data_setup_quality(request):
    result = []
    for q in range(1, 6):
        qs  = _closed_qs(request).filter(setup_quality=q)
        agg = qs.aggregate(avg_pnl=Avg('pnl'), count=Count('id'))
        wins = qs.filter(pnl__gt=0).count()
        total = agg['count'] or 0
        result.append({
            'quality': q,
            'avg_pnl': round(float(agg['avg_pnl'] or 0), 2),
            'win_rate': round(wins / total * 100, 1) if total else 0,
            'count': total,
        })
    return JsonResponse({'data': result})


def data_rule_review_summary(request):
    labels = ['Followed rules', 'Rule break', 'Not reviewed']
    configs = [
        ('FOLLOWED', _closed_qs(request).filter(rule_review=RuleReview.FOLLOWED)),
        ('BROKE', _closed_qs(request).filter(rule_review=RuleReview.BROKE)),
        ('UNREVIEWED', _closed_qs(request).filter(Q(rule_review__isnull=True) | Q(rule_review=''))),
    ]

    counts, avg_pnl, win_rates = [], [], []
    for _label, qs in configs:
        total = qs.count()
        counts.append(total)
        avg = qs.aggregate(avg=Avg('pnl'))['avg']
        avg_pnl.append(round(float(avg or 0), 2))
        win_rates.append(round(qs.filter(pnl__gt=0).count() / total * 100, 1) if total else 0)

    return JsonResponse({
        'labels': labels,
        'counts': counts,
        'avg_pnl': avg_pnl,
        'win_rates': win_rates,
    })


def data_rule_break_tags(request):
    tag_data: dict[str, dict] = defaultdict(lambda: {'count': 0, 'pnl': []})
    for row in _closed_qs(request).filter(rule_review=RuleReview.BROKE).values('rule_break_tags', 'pnl'):
        tags = row['rule_break_tags'] or ['Unspecified']
        for tag in tags:
            tag_data[tag]['count'] += 1
            tag_data[tag]['pnl'].append(float(row['pnl']))

    ranked = sorted(tag_data.items(), key=lambda item: (-item[1]['count'], sum(item[1]['pnl'])))[:8]
    labels = [item[0] for item in ranked]
    counts = [item[1]['count'] for item in ranked]
    avg_pnl = [round(sum(item[1]['pnl']) / len(item[1]['pnl']), 2) if item[1]['pnl'] else 0 for item in ranked]

    return JsonResponse({
        'labels': labels,
        'counts': counts,
        'avg_pnl': avg_pnl,
    })


def data_duration_vs_pnl(request):
    from datetime import datetime as dt, timedelta
    rows = _closed_qs(request).filter(
        exit_time__isnull=False
    ).values('entry_time', 'exit_time', 'pnl')[:500]
    points = []
    for r in rows:
        et = r['entry_time']
        xt = r['exit_time']
        # duration in minutes
        entry_mins = et.hour * 60 + et.minute
        exit_mins  = xt.hour * 60 + xt.minute
        duration   = exit_mins - entry_mins
        if duration > 0:
            points.append({'x': duration, 'y': float(r['pnl'])})
    return JsonResponse({'points': points})


def data_monthly_table(request):
    from itertools import groupby
    rows = _closed_qs(request).order_by('trade_date').values('trade_date', 'pnl', 'risk_reward_ratio')
    months: dict[str, dict] = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': Decimal('0'), 'rr_sum': Decimal('0'), 'rr_count': 0})
    for r in rows:
        key = r['trade_date'].strftime('%Y-%m')
        m   = months[key]
        m['trades'] += 1
        m['pnl']    += r['pnl']
        if r['pnl'] > 0:
            m['wins'] += 1
        if r['risk_reward_ratio']:
            m['rr_sum']   += r['risk_reward_ratio']
            m['rr_count'] += 1
    table = []
    for month, m in sorted(months.items()):
        table.append({
            'month': month,
            'trades': m['trades'],
            'win_rate': round(m['wins'] / m['trades'] * 100, 1) if m['trades'] else 0,
            'total_pnl': float(m['pnl']),
            'avg_rr': round(float(m['rr_sum'] / m['rr_count']), 2) if m['rr_count'] else None,
        })
    return JsonResponse({'table': table})
