import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import TradeForm, TradingSessionForm
from .models import OptionType, Trade, TradeStatus, TradeType, TradingSession
from .views import _compute_tag_stats


def _market_day(value=None):
	value = value or timezone.localdate()
	while value.weekday() >= 5:
		value -= datetime.timedelta(days=1)
	return value


class TradingSessionEmptyStateTests(TestCase):
	def test_dashboard_creates_blank_session_and_shows_prompt(self):
		today = _market_day()

		with patch('journal.views.timezone.localdate', return_value=today):
			response = self.client.get(reverse('dashboard'))

		session = TradingSession.objects.get(date=today)
		self.assertIsNone(session.market_bias)
		self.assertIsNone(session.psychological_state)
		self.assertContains(response, "Today's session plan is still blank.")

	def test_dashboard_shows_closed_trade_in_todays_trades(self):
		trade_date = _market_day()
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 15),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
		)

		trade = Trade.objects.get()
		with patch('journal.views.timezone.localdate', return_value=trade_date):
			response = self.client.get(reverse('dashboard'))

		self.assertContains(response, 'SPX CALL')
		self.assertContains(response, 'CLOSED')
		self.assertContains(response, '+$200.00')
		self.assertContains(response, reverse('trade_detail', args=[trade.pk]))
		self.assertNotContains(response, 'No trades for this session')

	def test_session_form_starts_unfilled_for_new_session(self):
		session = TradingSession.objects.create(date=_market_day())

		form = TradingSessionForm(instance=session)

		self.assertEqual(form.fields['market_bias'].choices[0], ('', 'Select market bias'))
		self.assertIsNone(form['market_bias'].value())
		self.assertIsNone(form['psychological_state'].value())

	def test_trade_auto_created_session_stays_blank_and_prompts_review(self):
		trade_date = _market_day()
		trade = Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			entry_time=datetime.time(9, 30),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.OPEN,
		)

		session = trade.session
		response = self.client.get(reverse('trade_detail', args=[trade.pk]))

		self.assertIsNotNone(session)
		self.assertIsNone(session.market_bias)
		self.assertIsNone(session.psychological_state)
		self.assertContains(response, 'Session setup was left blank.')

	def test_future_session_page_does_not_create_session_on_get(self):
		future_date = _market_day() + datetime.timedelta(days=14)
		while future_date.weekday() >= 5:
			future_date += datetime.timedelta(days=1)

		response = self.client.get(reverse('session_detail', args=[future_date.isoformat()]))

		self.assertEqual(response.status_code, 200)
		self.assertFalse(TradingSession.objects.filter(date=future_date).exists())
		self.assertContains(response, 'This session still needs a plan.')

	def test_dashboard_weekend_shows_market_closed_without_creating_session(self):
		saturday = datetime.date(2026, 4, 11)

		with patch('journal.views.timezone.localdate', return_value=saturday):
			response = self.client.get(reverse('dashboard'))

		self.assertFalse(TradingSession.objects.filter(date=saturday).exists())
		self.assertContains(response, 'Market is closed.')
		self.assertContains(response, 'Enjoy the weekend')

	def test_weekend_session_page_shows_closed_message_and_does_not_create_session(self):
		saturday = datetime.date(2026, 4, 11)

		response = self.client.get(reverse('session_detail', args=[saturday.isoformat()]))

		self.assertFalse(TradingSession.objects.filter(date=saturday).exists())
		self.assertContains(response, 'Weekend dates cannot have trading sessions or trades.')


class DashboardTagStatsTests(TestCase):
	def test_single_tag_does_not_render_as_both_best_and_worst(self):
		trade_date = _market_day()
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 15),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			strategy_tags=['Gap rules'],
		)

		stats = _compute_tag_stats(Trade.objects.all())
		response = self.client.get(reverse('dashboard'))

		self.assertEqual(stats['best_tag'], 'Gap rules')
		self.assertIsNone(stats['worst_tag'])
		self.assertContains(response, 'Best')
		self.assertContains(response, 'Gap rules', count=1)
		self.assertNotContains(response, 'Worst')


class TradeListTagFilterTests(TestCase):
	def test_trade_list_filters_by_partial_tag_match(self):
		trade_date = _market_day()
		matching_trade = Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 15),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			strategy_tags=['Gap rules', 'Morning breakout'],
		)
		Trade.objects.create(
			trade_date=trade_date,
			symbol='QQQ',
			option_type=OptionType.PUT,
			strike='430',
			expiry=trade_date,
			quantity=1,
			entry_price='4.00',
			entry_time=datetime.time(11, 0),
			trade_type=TradeType.LONG_PUT,
			status=TradeStatus.OPEN,
			strategy_tags=['Trend day'],
		)

		response = self.client.get(reverse('trade_list'), {'tag': 'gap'})

		self.assertContains(response, matching_trade.symbol)
		self.assertContains(response, 'Gap rules')
		self.assertNotContains(response, 'QQQ')

	def test_trade_list_shows_tags_column(self):
		trade_date = _market_day()
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			entry_time=datetime.time(9, 30),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.OPEN,
			strategy_tags=['Gap rules', 'Opening drive'],
		)

		response = self.client.get(reverse('trade_list'))

		self.assertContains(response, 'Tags')
		self.assertContains(response, 'Gap rules')
		self.assertContains(response, 'Opening drive')

	def test_trade_form_rejects_weekend_trade_date(self):
		form = TradeForm(data={
			'trade_date': '2026-04-11',
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': '2026-04-11',
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
		})

		self.assertFalse(form.is_valid())
		self.assertIn('trade_date', form.errors)

	def test_calendar_weekend_cells_are_not_clickable(self):
		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		self.assertNotContains(response, reverse('session_detail', args=['2026-04-11']))
		self.assertContains(response, 'Closed')
