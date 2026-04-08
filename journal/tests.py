import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import PerformanceGoalForm, TradeForm, TradingSessionForm
from .models import AppPreferences, OptionType, PerformanceGoal, RuleReview, Trade, TradeStatus, TradeType, TradingSession
from .templatetags.journal_extras import pnl_str
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

	def test_dashboard_holiday_shows_market_closed_without_creating_session(self):
		holiday = datetime.date(2026, 12, 25)

		with patch('journal.views.timezone.localdate', return_value=holiday):
			response = self.client.get(reverse('dashboard'))

		self.assertFalse(TradingSession.objects.filter(date=holiday).exists())
		self.assertContains(response, 'Market is closed.')
		self.assertContains(response, 'Christmas Day')

	def test_weekend_session_page_shows_closed_message_and_does_not_create_session(self):
		saturday = datetime.date(2026, 4, 11)

		response = self.client.get(reverse('session_detail', args=[saturday.isoformat()]))

		self.assertFalse(TradingSession.objects.filter(date=saturday).exists())
		self.assertContains(response, 'Weekend dates cannot have trading sessions or trades.')

	def test_holiday_session_page_shows_closed_message_and_does_not_create_session(self):
		holiday = datetime.date(2026, 12, 25)

		response = self.client.get(reverse('session_detail', args=[holiday.isoformat()]))

		self.assertFalse(TradingSession.objects.filter(date=holiday).exists())
		self.assertContains(response, 'Christmas Day is a market holiday')


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

	def test_trade_list_filters_by_rule_review(self):
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
			rule_review=RuleReview.FOLLOWED,
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
			rule_review=RuleReview.BROKE,
			rule_break_tags=['early entry'],
		)

		response = self.client.get(reverse('trade_list'), {'rule_review': 'BROKE'})

		self.assertContains(response, 'QQQ')
		self.assertNotContains(response, 'SPX')
		self.assertContains(response, 'Rules')

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

	def test_trade_form_rejects_market_holiday_trade_date(self):
		form = TradeForm(data={
			'trade_date': '2026-12-25',
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': '2026-12-25',
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
		})

		self.assertFalse(form.is_valid())
		self.assertIn('trade_date', form.errors)

	def test_trade_form_saves_rule_break_tracking(self):
		trade_date = _market_day()
		form = TradeForm(data={
			'trade_date': trade_date.isoformat(),
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': trade_date.isoformat(),
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
			'rule_review': RuleReview.BROKE,
			'rule_break_tags_text': 'early entry, oversized',
			'rule_break_notes': 'Chased the move instead of waiting for confirmation.',
		})

		self.assertTrue(form.is_valid(), form.errors)
		trade = form.save()
		self.assertEqual(trade.rule_review, RuleReview.BROKE)
		self.assertEqual(trade.rule_break_tags, ['early entry', 'oversized'])
		self.assertIn('waiting for confirmation', trade.rule_break_notes)

	def test_trade_form_requires_rule_break_context_when_marked_broke(self):
		trade_date = _market_day()
		form = TradeForm(data={
			'trade_date': trade_date.isoformat(),
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': trade_date.isoformat(),
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
			'rule_review': RuleReview.BROKE,
			'rule_break_tags_text': '',
			'rule_break_notes': '',
		})

		self.assertFalse(form.is_valid())
		self.assertIn('rule_break_tags_text', form.errors)

	def test_calendar_weekend_cells_are_not_clickable(self):
		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		self.assertNotContains(response, reverse('session_detail', args=['2026-04-11']))
		self.assertContains(response, 'Weekend')

	def test_calendar_holiday_cells_are_not_clickable(self):
		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 12})

		self.assertNotContains(response, reverse('session_detail', args=['2026-12-25']))
		self.assertContains(response, 'Christmas Day')


class DisplayCurrencyPreferenceTests(TestCase):
	@patch('journal.models.AppPreferences.fetch_usd_to_eur_rate', return_value=Decimal('0.9000'))
	def test_settings_page_updates_display_currency(self, mocked_fetch_rate):
		response = self.client.post(reverse('settings_index'), {'display_currency': 'EUR'}, follow=True)

		preferences = AppPreferences.objects.get(pk=1)

		self.assertEqual(preferences.display_currency, 'EUR')
		self.assertEqual(preferences.usd_to_eur_rate, Decimal('0.9000'))
		self.assertIsNotNone(preferences.exchange_rate_updated_at)
		mocked_fetch_rate.assert_called_once()
		self.assertContains(response, 'Display preferences updated.')

	def test_pnl_uses_selected_currency_but_trade_prices_stay_in_dollars(self):
		preferences = AppPreferences.objects.create(
			pk=1,
			display_currency='EUR',
			usd_to_eur_rate=Decimal('0.9000'),
			exchange_rate_updated_at=timezone.now(),
		)
		preferences.save()

		trade_date = _market_day()
		trade = Trade.objects.create(
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

		response = self.client.get(reverse('trade_detail', args=[trade.pk]))

		self.assertEqual(pnl_str(Decimal('200')), '+€180.00')
		self.assertContains(response, '+€180.00')
		self.assertContains(response, '$5.00')
		self.assertContains(response, '$7.00')

	@patch('journal.models.AppPreferences.fetch_usd_to_eur_rate', side_effect=ValueError('service unavailable'))
	def test_pnl_falls_back_to_saved_rate_when_live_fetch_fails(self, mocked_fetch_rate):
		preferences = AppPreferences.objects.create(
			pk=1,
			display_currency='EUR',
			usd_to_eur_rate=Decimal('0.9100'),
		)

		self.assertEqual(preferences.convert_pnl_value(Decimal('100')), Decimal('91.00'))
		mocked_fetch_rate.assert_called_once()

	def test_settings_page_updates_rule_break_presets(self):
		response = self.client.post(reverse('settings_index'), {
			'save_rule_break_tags': '1',
			'rule_break_tag_templates_text': 'early entry\noversized\nrevenge trade',
		}, follow=True)

		preferences = AppPreferences.objects.get(pk=1)

		self.assertEqual(preferences.rule_break_tag_templates, ['early entry', 'oversized', 'revenge trade'])
		self.assertContains(response, 'Rule-break presets updated.')
		self.assertContains(response, 'revenge trade')


class PerformanceGoalTests(TestCase):
	def test_process_goal_form_allows_non_numeric_goal(self):
		form = PerformanceGoalForm(data={
			'title': 'Follow the rules',
			'description': 'Execute only valid setups and skip revenge trades.',
			'metric': '',
			'target_value': '',
			'current_value': '',
			'period': 'WEEKLY',
			'start_date': '2026-04-06',
			'end_date': '',
			'status': 'ACTIVE',
		})

		self.assertTrue(form.is_valid(), form.errors)
		goal = form.save()
		self.assertIsNone(goal.metric)
		self.assertIsNone(goal.target_value)
		self.assertIsNone(goal.current_value)
		self.assertIsNone(goal.end_date)

	def test_goal_form_allows_missing_end_date_for_quantitative_goal(self):
		form = PerformanceGoalForm(data={
			'title': 'Reach 10 trades',
			'description': '',
			'metric': 'TRADE_COUNT',
			'target_value': '10',
			'current_value': '',
			'period': 'MONTHLY',
			'start_date': '2026-04-01',
			'end_date': '',
			'status': 'ACTIVE',
		})

		self.assertTrue(form.is_valid(), form.errors)

	def test_quantitative_goal_still_requires_target(self):
		form = PerformanceGoalForm(data={
			'title': 'Increase win rate',
			'description': '',
			'metric': 'WIN_RATE',
			'target_value': '',
			'current_value': '65',
			'period': 'MONTHLY',
			'start_date': '2026-04-01',
			'end_date': '2026-04-30',
			'status': 'ACTIVE',
		})

		self.assertFalse(form.is_valid())
		self.assertIn('target_value', form.errors)

	def test_goals_page_renders_process_goal_without_numeric_target(self):
		PerformanceGoal.objects.create(
			title='Follow the rules',
			description='Take only valid setups.',
			period='WEEKLY',
			start_date=datetime.date(2026, 4, 6),
			end_date=datetime.date(2026, 4, 10),
			status='ACTIVE',
		)

		response = self.client.get(reverse('goals'))

		self.assertContains(response, 'Follow the rules')
		self.assertContains(response, 'Process Goal')
		self.assertNotContains(response, 'target None')


class RuleTrackingAnalyticsTests(TestCase):
	def test_rule_review_summary_endpoint_returns_followed_and_broken_stats(self):
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
			rule_review=RuleReview.FOLLOWED,
		)
		Trade.objects.create(
			trade_date=trade_date,
			symbol='QQQ',
			option_type=OptionType.PUT,
			strike='430',
			expiry=trade_date,
			quantity=1,
			entry_price='4.00',
			exit_price='3.00',
			entry_time=datetime.time(11, 0),
			exit_time=datetime.time(11, 45),
			trade_type=TradeType.LONG_PUT,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.BROKE,
			rule_break_tags=['early entry'],
		)

		response = self.client.get(reverse('data_rule_review_summary'))
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload['labels'][0], 'Followed rules')
		self.assertEqual(payload['counts'], [1, 1, 0])

	def test_rule_break_tags_endpoint_groups_rule_breaks(self):
		trade_date = _market_day()
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='4.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(9, 50),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.BROKE,
			rule_break_tags=['oversized', 'early entry'],
		)

		response = self.client.get(reverse('data_rule_break_tags'))
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertIn('oversized', payload['labels'])
		self.assertIn('early entry', payload['labels'])


class DashboardRuleMetricTests(TestCase):
	def test_dashboard_shows_rule_metrics(self):
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
			rule_review=RuleReview.FOLLOWED,
		)
		Trade.objects.create(
			trade_date=trade_date,
			symbol='QQQ',
			option_type=OptionType.PUT,
			strike='430',
			expiry=trade_date,
			quantity=1,
			entry_price='4.00',
			exit_price='3.00',
			entry_time=datetime.time(11, 0),
			exit_time=datetime.time(11, 45),
			trade_type=TradeType.LONG_PUT,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.BROKE,
			rule_break_tags=['early entry'],
		)

		with patch('journal.views.timezone.localdate', return_value=trade_date):
			response = self.client.get(reverse('dashboard'))

		self.assertContains(response, 'Rule Follow Rate (7d)')
		self.assertContains(response, '50.0%')
		self.assertContains(response, 'Most Common Rule Break (30d)')
		self.assertContains(response, 'early entry')

	def test_dashboard_shows_all_top_rule_break_tags_when_tied(self):
		trade_date = _market_day()
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='4.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(9, 50),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.BROKE,
			rule_break_tags=['oversized', 'early entry'],
		)

		with patch('journal.views.timezone.localdate', return_value=trade_date):
			response = self.client.get(reverse('dashboard'))

		self.assertContains(response, 'oversized')
		self.assertContains(response, 'early entry')
		self.assertContains(response, 'Logged 1 time across closed trades')
		self.assertContains(response, 'each')
