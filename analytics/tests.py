import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from journal.models import (
	EntryType, JournalEntry, OptionType, RuleReview,
	Trade, TradeStatus, TradeType, TradingSession,
)


def _market_day(value=None):
	value = value or timezone.localdate()
	while value.weekday() >= 5:
		value -= datetime.timedelta(days=1)
	return value


def _make_trade(trade_date, entry_price='5.00', exit_price='7.00',
				status=TradeStatus.CLOSED, is_paper_trade=False, **kwargs):
	defaults = dict(
		symbol='SPX',
		option_type=OptionType.CALL,
		trade_type=TradeType.LONG_CALL,
		strike='5000',
		expiry=trade_date,
		quantity=1,
		entry_time=datetime.time(9, 30),
		exit_time=datetime.time(10, 0),
	)
	defaults.update(kwargs)
	return Trade.objects.create(
		trade_date=trade_date,
		entry_price=entry_price,
		exit_price=exit_price,
		status=status,
		is_paper_trade=is_paper_trade,
		**defaults,
	)


# ---------------------------------------------------------------------------
# Monthly Performance endpoint
# ---------------------------------------------------------------------------

class MonthlyTablePaperSeparationTests(TestCase):
	"""data_monthly_table splits real vs paper P&L per month."""

	def test_real_and_paper_pnl_are_separate_in_response(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='7.00')            # +$200 real
		_make_trade(day, entry_price='5.00', exit_price='9.00',            # +$400 paper
					is_paper_trade=True)

		response = self.client.get(reverse('data_monthly_table'))
		data = response.json()

		self.assertEqual(response.status_code, 200)
		row = data['table'][0]
		self.assertEqual(row['month'], '2026-04')
		self.assertAlmostEqual(row['total_pnl'], 200.0)
		self.assertAlmostEqual(row['paper_pnl'], 400.0)
		self.assertEqual(row['trades'], 1)
		self.assertEqual(row['paper_trades'], 1)

	def test_real_trades_only_no_paper_fields_zero(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='7.00')

		response = self.client.get(reverse('data_monthly_table'))
		data = response.json()
		row = data['table'][0]

		self.assertAlmostEqual(row['total_pnl'], 200.0)
		self.assertAlmostEqual(row['paper_pnl'], 0.0)
		self.assertEqual(row['paper_trades'], 0)

	def test_paper_trades_only_total_pnl_is_zero(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, is_paper_trade=True)

		response = self.client.get(reverse('data_monthly_table'))
		data = response.json()
		row = data['table'][0]

		self.assertAlmostEqual(row['total_pnl'], 0.0)
		self.assertAlmostEqual(row['paper_pnl'], 200.0)
		self.assertEqual(row['trades'], 0)
		self.assertEqual(row['paper_trades'], 1)

	def test_win_rate_only_counts_real_trades(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='7.00')                # win real
		_make_trade(day, entry_price='5.00', exit_price='3.00')                # loss real
		_make_trade(day, entry_price='5.00', exit_price='9.00', is_paper_trade=True)  # win paper (ignored)

		response = self.client.get(reverse('data_monthly_table'))
		data = response.json()
		row = data['table'][0]

		self.assertEqual(row['win_rate'], 50.0)
		self.assertEqual(row['trades'], 2)

	def test_multiple_months_are_each_correct(self):
		_make_trade(datetime.date(2026, 3, 31), entry_price='5.00', exit_price='7.00')  # +$200 Mar real
		_make_trade(datetime.date(2026, 4, 8),  entry_price='5.00', exit_price='9.00',  # +$400 Apr paper
					is_paper_trade=True)

		response = self.client.get(reverse('data_monthly_table'))
		data = response.json()
		by_month = {r['month']: r for r in data['table']}

		self.assertAlmostEqual(by_month['2026-03']['total_pnl'], 200.0)
		self.assertAlmostEqual(by_month['2026-03']['paper_pnl'], 0.0)
		self.assertAlmostEqual(by_month['2026-04']['total_pnl'], 0.0)
		self.assertAlmostEqual(by_month['2026-04']['paper_pnl'], 400.0)


# ---------------------------------------------------------------------------
# Weekly review — paper / real separation
# ---------------------------------------------------------------------------

class WeeklyReviewPaperSeparationTests(TestCase):
	"""performance_review stats are real-only; paper counts shown separately."""

	def test_total_pnl_stat_excludes_paper_trades(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='7.00')             # +$200 real
		_make_trade(day, entry_price='5.00', exit_price='25.00',            # +$2000 paper
					is_paper_trade=True)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertEqual(response.context['stats']['total_pnl'], Decimal('200.00'))
		self.assertEqual(response.context['stats']['paper_pnl'], Decimal('2000.00'))

	def test_closed_trades_count_excludes_paper(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day)
		_make_trade(day, is_paper_trade=True)
		_make_trade(day, is_paper_trade=True)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertEqual(response.context['stats']['closed_trades'], 1)
		self.assertEqual(response.context['stats']['paper_trade_count'], 2)

	def test_win_rate_excludes_paper_trades(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='7.00')             # win real
		_make_trade(day, entry_price='5.00', exit_price='3.00')             # loss real
		_make_trade(day, entry_price='5.00', exit_price='9.00', is_paper_trade=True)  # win paper

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertEqual(response.context['stats']['win_rate'], 50.0)

	def test_paper_pnl_annotation_appears_in_review_html(self):
		day = datetime.date(2026, 4, 8)
		_make_trade(day, entry_price='5.00', exit_price='9.00', is_paper_trade=True)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'paper')
		self.assertContains(response, '#fbbf24')


# ---------------------------------------------------------------------------
# Weekly review — best/worst trade priority
# ---------------------------------------------------------------------------

class WeeklyReviewBestWorstPriorityTests(TestCase):
	"""Real trades fill best/worst slots first; paper fills remaining vacancies."""

	def test_real_trades_fill_best_slots_before_paper(self):
		day = datetime.date(2026, 4, 8)
		# 3 real winners
		for i, exit_price in enumerate(['10.00', '9.00', '8.00'], start=1):
			_make_trade(day, strike=f'500{i}', entry_price='5.00', exit_price=exit_price,
						trade_notes=f'Real win {i}')
		# 1 bigger paper winner – should NOT displace any real trade
		_make_trade(day, strike='5099', entry_price='5.00', exit_price='50.00',
					is_paper_trade=True, trade_notes='Paper big win')

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'Real win 1')
		self.assertContains(response, 'Real win 2')
		self.assertContains(response, 'Real win 3')
		self.assertNotContains(response, 'Paper big win')

	def test_paper_fills_remaining_best_slots_when_fewer_than_three_real(self):
		day = datetime.date(2026, 4, 8)
		# 1 real winner
		_make_trade(day, strike='5001', entry_price='5.00', exit_price='7.00',
					trade_notes='Only real win')
		# 2 paper winners to fill slots 2 & 3
		_make_trade(day, strike='5002', entry_price='5.00', exit_price='8.00',
					is_paper_trade=True, trade_notes='Paper fill 1')
		_make_trade(day, strike='5003', entry_price='5.00', exit_price='9.00',
					is_paper_trade=True, trade_notes='Paper fill 2')

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'Only real win')
		self.assertContains(response, 'Paper fill 1')
		self.assertContains(response, 'Paper fill 2')

	def test_real_trades_fill_worst_slots_before_paper(self):
		day = datetime.date(2026, 4, 8)
		# 3 real losers
		for i, exit_price in enumerate(['2.00', '3.00', '4.00'], start=1):
			_make_trade(day, strike=f'600{i}', entry_price='5.00', exit_price=exit_price,
						rule_break_notes=f'Real loss {i}')
		# 1 bigger paper loser – should NOT displace any real trade
		_make_trade(day, strike='6099', entry_price='5.00', exit_price='0.01',
					is_paper_trade=True, rule_break_notes='Paper big loss')

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'Real loss 1')
		self.assertContains(response, 'Real loss 2')
		self.assertContains(response, 'Real loss 3')
		self.assertNotContains(response, 'Paper big loss')

	def test_paper_badge_shown_in_best_trades_when_paper_fills_slot(self):
		day = datetime.date(2026, 4, 8)
		# no real winners, one paper winner
		_make_trade(day, entry_price='5.00', exit_price='9.00',
					is_paper_trade=True, trade_notes='Paper winner')

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'PAPER')


# ---------------------------------------------------------------------------
# Weekly review — session timeline rows carry paper data
# ---------------------------------------------------------------------------

class WeeklyReviewTimelineTests(TestCase):
	"""session_rows passed to the template carry paper_count and paper_pnl."""

	def test_session_row_paper_count_and_pnl_populated(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session)                                    # real
		_make_trade(day, session=session, entry_price='5.00', exit_price='9.00',
					is_paper_trade=True)                                     # paper +$400

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		rows = {r['date']: r for r in response.context['session_rows']}
		wednesday = rows[day]
		self.assertEqual(wednesday['paper_count'], 1)
		self.assertEqual(wednesday['paper_pnl'], Decimal('400.00'))

	def test_session_row_pnl_is_real_only(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')   # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='25.00',  # +$2000 paper
					is_paper_trade=True)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		rows = {r['date']: r for r in response.context['session_rows']}
		self.assertEqual(rows[day]['pnl'], Decimal('200.00'))

	def test_session_row_paper_annotation_renders_in_html(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, is_paper_trade=True)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertContains(response, 'paper')
