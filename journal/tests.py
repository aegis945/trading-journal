import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import TradingSessionForm
from .models import OptionType, Trade, TradeStatus, TradeType, TradingSession
from .views import _compute_tag_stats


class TradingSessionEmptyStateTests(TestCase):
	def test_dashboard_creates_blank_session_and_shows_prompt(self):
		today = timezone.localdate()

		response = self.client.get(reverse('dashboard'))

		session = TradingSession.objects.get(date=today)
		self.assertIsNone(session.market_bias)
		self.assertIsNone(session.psychological_state)
		self.assertContains(response, "Today's session plan is still blank.")

	def test_dashboard_shows_closed_trade_in_todays_trades(self):
		trade_date = timezone.localdate()
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
		response = self.client.get(reverse('dashboard'))

		self.assertContains(response, 'SPX CALL')
		self.assertContains(response, 'CLOSED')
		self.assertContains(response, '+$200.00')
		self.assertContains(response, reverse('trade_detail', args=[trade.pk]))
		self.assertNotContains(response, 'No trades for this session')

	def test_session_form_starts_unfilled_for_new_session(self):
		session = TradingSession.objects.create(date=timezone.localdate())

		form = TradingSessionForm(instance=session)

		self.assertEqual(form.fields['market_bias'].choices[0], ('', 'Select market bias'))
		self.assertIsNone(form['market_bias'].value())
		self.assertIsNone(form['psychological_state'].value())

	def test_trade_auto_created_session_stays_blank_and_prompts_review(self):
		trade_date = timezone.localdate()
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


class DashboardTagStatsTests(TestCase):
	def test_single_tag_does_not_render_as_both_best_and_worst(self):
		trade_date = timezone.localdate()
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
		trade_date = timezone.localdate()
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
		trade_date = timezone.localdate()
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
