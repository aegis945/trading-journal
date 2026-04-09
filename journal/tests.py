import datetime
import os
import shutil
import tempfile
import unittest.mock
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import PerformanceGoalForm, TradeForm, TradingSessionForm
from .models import AppPreferences, EntryType, JournalEntry, OptionType, PerformanceGoal, ProcessMetric, RuleReview, Trade, TradeStatus, TradeType, TradingSession, calculate_process_metrics
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
		self.assertContains(response, 'Fill it out')

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


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class TradeScreenshotActionTests(TestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

	def test_trade_edit_shows_direct_delete_screenshot_action(self):
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
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
		)
		trade.ta_screenshot = SimpleUploadedFile(
			'chart.gif',
			b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
			content_type='image/gif',
		)
		trade.save()

		response = self.client.get(reverse('trade_edit', args=[trade.pk]))

		self.assertContains(response, 'Delete screenshot')
		self.assertContains(response, reverse('trade_screenshot_delete', args=[trade.pk]))

	def test_trade_screenshot_delete_removes_file_and_returns_to_edit(self):
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
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
		)
		trade.ta_screenshot = SimpleUploadedFile(
			'chart.gif',
			b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
			content_type='image/gif',
		)
		trade.save()
		screenshot_path = trade.ta_screenshot.path

		response = self.client.post(reverse('trade_screenshot_delete', args=[trade.pk]), follow=True)

		trade.refresh_from_db()
		self.assertRedirects(response, reverse('trade_edit', args=[trade.pk]))
		self.assertFalse(trade.ta_screenshot)
		self.assertFalse(os.path.exists(screenshot_path))
		self.assertContains(response, 'Screenshot deleted. You can upload a new one now.')

	def test_dashboard_prompts_for_missing_post_session_reflection_when_trades_exist(self):
		trade_date = _market_day()
		session = TradingSession.objects.create(
			date=trade_date,
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Ready for the open.',
		)
		Trade.objects.create(
			session=session,
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
		)

		with patch('journal.views.timezone.localdate', return_value=trade_date):
			response = self.client.get(reverse('dashboard'))

		self.assertContains(response, 'This session has trades but no reflection.')
		self.assertContains(response, 'Add reflection')


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
		self.assertEqual(trade.rule_break_tags, ['Early entry', 'Oversized'])
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

	def test_trade_add_defaults_contract_quantity_to_one(self):
		response = self.client.get(reverse('trade_add'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="quantity"')
		self.assertContains(response, 'value="1"', html=False)

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
	def test_calculate_process_metrics_returns_scored_percentages(self):
		trade_date = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(
			date=trade_date,
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Ready for the open.',
			session_notes='Reviewed the session afterward.',
		)
		Trade.objects.create(
			session=session,
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.FOLLOWED,
		)

		metrics = calculate_process_metrics(trade_date, trade_date)

		self.assertEqual(metrics[ProcessMetric.FOLLOW_RULES], 100.0)
		self.assertEqual(metrics[ProcessMetric.SESSION_PREP], 100.0)
		self.assertEqual(metrics[ProcessMetric.SESSION_REVIEW], 100.0)
		self.assertEqual(metrics[ProcessMetric.PROCESS_SCORE], 100.0)
		self.assertEqual(metrics['trading_day_count'], 1)

	def test_process_metrics_ignore_sessions_without_trades(self):
		trade_date = datetime.date(2026, 4, 8)
		TradingSession.objects.create(
			date=trade_date - datetime.timedelta(days=1),
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Planned but skipped the session.',
			session_notes='No trades were taken.',
		)
		session = TradingSession.objects.create(
			date=trade_date,
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Ready for the open.',
			session_notes='Reviewed the active session.',
		)
		Trade.objects.create(
			session=session,
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.FOLLOWED,
		)

		metrics = calculate_process_metrics(trade_date - datetime.timedelta(days=1), trade_date)

		self.assertEqual(metrics[ProcessMetric.SESSION_PREP], 100.0)
		self.assertEqual(metrics[ProcessMetric.SESSION_REVIEW], 100.0)
		self.assertEqual(metrics['trading_day_count'], 1)

	def test_process_goal_form_allows_non_numeric_goal(self):
		form = PerformanceGoalForm(data={
			'title': 'Follow the rules',
			'description': 'Execute only valid setups and skip revenge trades.',
			'process_metric': '',
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
		self.assertIsNone(goal.process_metric)

	def test_process_goal_form_allows_automatic_process_tracking(self):
		form = PerformanceGoalForm(data={
			'title': 'Follow the rules',
			'description': 'Let the app score my process discipline.',
			'process_metric': ProcessMetric.FOLLOW_RULES,
			'metric': '',
			'target_value': '90',
			'current_value': '',
			'period': 'WEEKLY',
			'start_date': '2026-04-06',
			'end_date': '',
			'status': 'ACTIVE',
		})

		self.assertTrue(form.is_valid(), form.errors)
		goal = form.save()
		self.assertEqual(goal.process_metric, ProcessMetric.FOLLOW_RULES)
		self.assertIsNone(goal.metric)
		self.assertIsNone(goal.current_value)

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

	def test_goals_page_renders_tracked_process_goal_progress(self):
		trade_date = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(
			date=trade_date,
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Prepared before the bell.',
		)
		Trade.objects.create(
			session=session,
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 0),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			rule_review=RuleReview.FOLLOWED,
		)
		PerformanceGoal.objects.create(
			title='Rules first',
			description='Track weekly rule-follow rate.',
			process_metric=ProcessMetric.FOLLOW_RULES,
			target_value=Decimal('90'),
			period='WEEKLY',
			start_date=datetime.date(2026, 4, 6),
			status='ACTIVE',
		)

		response = self.client.get(reverse('goals'))

		self.assertContains(response, 'Rules first')
		self.assertContains(response, 'Follow Rules (%)')
		self.assertContains(response, '100.0 / 90.0%')
		self.assertContains(response, 'Auto-scored from your logged trades and sessions.')


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


class WeeklyReviewTests(TestCase):
	def test_weekly_review_aggregates_existing_trade_session_and_journal_data(self):
		trade_date = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(
			date=trade_date,
			market_bias='BULLISH',
			psychological_state=4,
			market_open_notes='Wait for confirmation at the open.',
			session_notes='Stayed patient and only took one clean setup.',
		)
		trade = Trade.objects.create(
			session=session,
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.CALL,
			strike='5000',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='7.00',
			entry_time=datetime.time(9, 30),
			exit_time=datetime.time(10, 5),
			trade_type=TradeType.LONG_CALL,
			status=TradeStatus.CLOSED,
			strategy_tags=['Opening drive'],
			rule_review=RuleReview.FOLLOWED,
			trade_notes='Waited for reclaim and took the retest entry.',
		)
		entry = JournalEntry.objects.create(
			title='Weekly lesson',
			content='Patience improved my entries this week.',
			entry_type=EntryType.LESSON,
			session=session,
		)
		entry.trades.add(trade)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-07'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Weekly Review')
		self.assertContains(response, '+$200.00')
		self.assertContains(response, 'Process Score')
		self.assertContains(response, '100.0%')
		self.assertContains(response, '1/1')
		self.assertContains(response, 'Opening drive')
		self.assertContains(response, 'Stayed patient and only took one clean setup.')
		self.assertContains(response, 'Weekly lesson')
		self.assertContains(response, 'Best 3 Trades')
		self.assertContains(response, 'No losing trades yet this week.')

	def test_weekly_review_defaults_to_latest_activity_week(self):
		older_date = datetime.date(2026, 3, 31)
		latest_date = datetime.date(2026, 4, 8)
		Trade.objects.create(
			trade_date=older_date,
			symbol='QQQ',
			option_type=OptionType.PUT,
			strike='430',
			expiry=older_date,
			quantity=1,
			entry_price='4.00',
			exit_price='3.00',
			entry_time=datetime.time(10, 0),
			exit_time=datetime.time(10, 30),
			trade_type=TradeType.LONG_PUT,
			status=TradeStatus.CLOSED,
		)
		JournalEntry.objects.create(
			title='Latest note',
			content='This should anchor the latest review week.',
			entry_type=EntryType.OBSERVATION,
			created_at=timezone.make_aware(datetime.datetime(2026, 4, 8, 12, 0)),
		)

		response = self.client.get(reverse('performance_review'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Week of Apr 6 - Apr 12, 2026')
		self.assertContains(response, 'Latest note')

	def test_weekly_review_shows_worst_trade_only_for_losses(self):
		trade_date = datetime.date(2026, 4, 8)
		Trade.objects.create(
			trade_date=trade_date,
			symbol='SPX',
			option_type=OptionType.PUT,
			strike='6780',
			expiry=trade_date,
			quantity=1,
			entry_price='5.00',
			exit_price='11.32',
			entry_time=datetime.time(9, 35),
			exit_time=datetime.time(10, 5),
			trade_type=TradeType.LONG_PUT,
			status=TradeStatus.CLOSED,
			trade_notes='Profited from the opening flush.',
		)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-08'})

		self.assertContains(response, 'Best 3 Trades')
		self.assertContains(response, 'Profited from the opening flush.')
		self.assertContains(response, 'No losing trades yet this week.')

	def test_weekly_review_shows_top_three_best_and_worst_trades(self):
		trade_date = datetime.date(2026, 4, 8)
		for index, exit_price in enumerate(['8.00', '7.00', '6.00', '5.50'], start=1):
			Trade.objects.create(
				trade_date=trade_date,
				symbol='SPX',
				option_type=OptionType.CALL,
				strike=f'500{index}',
				expiry=trade_date,
				quantity=1,
				entry_price='5.00',
				exit_price=exit_price,
				entry_time=datetime.time(9, 30 + index),
				exit_time=datetime.time(10, 0 + index),
				trade_type=TradeType.LONG_CALL,
				status=TradeStatus.CLOSED,
				trade_notes=f'Winning trade {index}',
			)
		for index, exit_price in enumerate(['2.00', '3.00', '4.00', '4.50'], start=1):
			Trade.objects.create(
				trade_date=trade_date,
				symbol='QQQ',
				option_type=OptionType.PUT,
				strike=f'430{index}',
				expiry=trade_date,
				quantity=1,
				entry_price='5.00',
				exit_price=exit_price,
				entry_time=datetime.time(11, 0 + index),
				exit_time=datetime.time(11, 20 + index),
				trade_type=TradeType.LONG_PUT,
				status=TradeStatus.CLOSED,
				rule_break_notes=f'Losing trade {index}',
			)

		response = self.client.get(reverse('performance_review'), {'week': '2026-04-08'})

		self.assertContains(response, 'Best 3 Trades')
		self.assertContains(response, 'Worst 3 Trades')
		self.assertContains(response, 'Winning trade 1')
		self.assertContains(response, 'Winning trade 2')
		self.assertContains(response, 'Winning trade 3')
		self.assertNotContains(response, 'Winning trade 4')
		self.assertContains(response, 'Losing trade 1')
		self.assertContains(response, 'Losing trade 2')
		self.assertContains(response, 'Losing trade 3')
		self.assertNotContains(response, 'Losing trade 4')

	def test_weekly_review_prompts_for_missing_weekly_note_when_rule_breaks_exist(self):
		trade_date = datetime.date(2026, 4, 8)
		for index in range(3):
			Trade.objects.create(
				trade_date=trade_date,
				symbol='SPX',
				option_type=OptionType.PUT,
				strike=f'678{index}',
				expiry=trade_date,
				quantity=1,
				entry_price='5.00',
				exit_price='4.00',
				entry_time=datetime.time(9, 30 + index),
				exit_time=datetime.time(9, 45 + index),
				trade_type=TradeType.LONG_PUT,
				status=TradeStatus.CLOSED,
				rule_review=RuleReview.BROKE,
				rule_break_tags=['early entry'],
			)

		# Prompt only shows on the last trading day of the week — mock to Friday Apr 10
		with unittest.mock.patch('analytics.views.timezone') as mock_tz:
			mock_tz.localdate.return_value = datetime.date(2026, 4, 10)
			mock_tz.localtime = timezone.localtime
			response = self.client.get(reverse('performance_review'), {'week': '2026-04-06'})

		self.assertContains(response, 'This week has 3 rule-break trades and no weekly note.')
		self.assertContains(response, 'Write note')


# ---------------------------------------------------------------------------
# Paper trade regression tests
# ---------------------------------------------------------------------------

def _make_trade(trade_date, symbol='SPX', option_type=None, trade_type=None,
				entry_price='5.00', exit_price='7.00', status=None,
				entry_time=None, exit_time=None, is_paper_trade=False, **kwargs):
	"""Helper that creates a minimal closed trade."""
	option_type = option_type or OptionType.CALL
	trade_type = trade_type or TradeType.LONG_CALL
	status = status or TradeStatus.CLOSED
	entry_time = entry_time or datetime.time(9, 30)
	exit_time = exit_time or datetime.time(10, 0)
	return Trade.objects.create(
		trade_date=trade_date,
		symbol=symbol,
		option_type=option_type,
		trade_type=trade_type,
		strike='5000',
		expiry=trade_date,
		quantity=1,
		entry_price=entry_price,
		exit_price=exit_price,
		entry_time=entry_time,
		exit_time=exit_time,
		status=status,
		is_paper_trade=is_paper_trade,
		**kwargs,
	)


class PaperTradeModelTests(TestCase):
	"""TradingSession.real_pnl and .paper_pnl only count the right trades."""

	def test_real_pnl_excludes_paper_trades(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')           # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='9.00',           # +$400 paper
					is_paper_trade=True)

		self.assertEqual(session.real_pnl, Decimal('200.00'))

	def test_paper_pnl_excludes_real_trades(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')           # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='9.00',           # +$400 paper
					is_paper_trade=True)

		self.assertEqual(session.paper_pnl, Decimal('400.00'))

	def test_real_pnl_is_zero_when_only_paper_trades_exist(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='9.00', is_paper_trade=True)

		self.assertEqual(session.real_pnl, Decimal('0'))

	def test_paper_pnl_is_zero_when_only_real_trades_exist(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')

		self.assertEqual(session.paper_pnl, Decimal('0'))

	def test_open_paper_trades_not_counted_in_paper_pnl(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		Trade.objects.create(
			trade_date=day, session=session, symbol='SPX',
			option_type=OptionType.CALL, trade_type=TradeType.LONG_CALL,
			strike='5000', expiry=day, quantity=1, entry_price='5.00',
			entry_time=datetime.time(9, 30), status=TradeStatus.OPEN,
			is_paper_trade=True,
		)

		self.assertEqual(session.paper_pnl, Decimal('0'))


class PaperTradeSessionDetailTests(TestCase):
	"""Session detail page displays real and paper trades in separate sections."""

	def test_session_detail_separates_real_and_paper_trades(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')
		_make_trade(day, session=session, entry_price='5.00', exit_price='9.00', is_paper_trade=True)

		response = self.client.get(reverse('session_detail', args=[day.isoformat()]))

		self.assertContains(response, 'Paper Trades')
		self.assertContains(response, 'Live P&L')

	def test_session_detail_live_pnl_header_uses_real_only(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')          # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='15.00',          # +$1000 paper
					is_paper_trade=True)

		response = self.client.get(reverse('session_detail', args=[day.isoformat()]))

		# Real P&L should appear, not the inflated total
		self.assertContains(response, '+$200.00')
		self.assertNotContains(response, '+$1,200.00')

	def test_session_detail_no_paper_section_when_no_paper_trades(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session)

		response = self.client.get(reverse('session_detail', args=[day.isoformat()]))

		self.assertNotContains(response, 'Paper Trades')
		self.assertContains(response, 'Session P&L')

	def test_session_detail_context_contains_split_querysets(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		real = _make_trade(day, session=session)
		paper = _make_trade(day, session=session, is_paper_trade=True)

		response = self.client.get(reverse('session_detail', args=[day.isoformat()]))

		real_ids = list(response.context['real_trades'].values_list('pk', flat=True))
		paper_ids = list(response.context['paper_trades'].values_list('pk', flat=True))
		self.assertIn(real.pk, real_ids)
		self.assertNotIn(paper.pk, real_ids)
		self.assertIn(paper.pk, paper_ids)
		self.assertNotIn(real.pk, paper_ids)


class PaperTradeSessionListTests(TestCase):
	"""Sessions list page shows real P&L and paper P&L annotated separately."""

	def test_session_list_shows_real_pnl_not_combined(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')           # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='25.00',           # +$2000 paper
					is_paper_trade=True)

		response = self.client.get(reverse('session_list'))

		self.assertContains(response, '+$200.00')
		self.assertNotContains(response, '+$2,200.00')

	def test_session_list_shows_paper_pnl_annotation_in_yellow(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, is_paper_trade=True,
					entry_price='5.00', exit_price='9.00')   # +$400 paper

		response = self.client.get(reverse('session_list'))

		# Template uses inline style with #fbbf24 on the paper annotation
		self.assertContains(response, 'paper')
		self.assertContains(response, '#fbbf24')

	def test_session_list_no_paper_annotation_when_only_real_trades(self):
		day = _market_day()
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session)

		response = self.client.get(reverse('session_list'))

		self.assertNotContains(response, 'paper')


class PaperTradeCalendarTests(TestCase):
	"""Calendar cells show real P&L in green/red and paper P&L in yellow."""

	def test_calendar_cell_pnl_is_real_only(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='7.00')           # +$200 real
		_make_trade(day, session=session, entry_price='5.00', exit_price='25.00',           # +$2000 paper
					is_paper_trade=True)

		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		self.assertContains(response, '+$200')
		self.assertNotContains(response, '+$2,200')

	def test_calendar_shows_paper_annotation(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, is_paper_trade=True,
					entry_price='5.00', exit_price='9.00')  # +$400 paper only

		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		self.assertContains(response, 'paper')
		self.assertContains(response, '#fbbf24')

	def test_calendar_no_paper_annotation_when_only_real_trades(self):
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session)

		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		self.assertNotContains(response, 'paper')

	def test_calendar_cell_background_driven_by_real_pnl(self):
		"""A day that is a real loss but a paper gain should show loss background."""
		day = datetime.date(2026, 4, 8)
		session = TradingSession.objects.create(date=day)
		_make_trade(day, session=session, entry_price='5.00', exit_price='3.00')           # -$200 real loss
		_make_trade(day, session=session, entry_price='5.00', exit_price='25.00',           # +$2000 paper gain
					is_paper_trade=True)

		response = self.client.get(reverse('calendar'), {'year': 2026, 'month': 4})

		# Inline cell styles use no-space format; base CSS hover rules use 'background: var(--profit-glow)' with space
		self.assertContains(response, 'background:var(--loss-glow)')
		self.assertNotContains(response, 'background:var(--profit-glow)')


class PaperTradeTradeListTests(TestCase):
	"""Trade log shows PAPER badge and yellow P&L for paper trades."""

	def test_trade_list_shows_paper_badge(self):
		day = _market_day()
		_make_trade(day, is_paper_trade=True)

		response = self.client.get(reverse('trade_list'))

		self.assertContains(response, 'PAPER')

	def test_trade_list_real_trade_has_no_paper_badge(self):
		day = _market_day()
		_make_trade(day, is_paper_trade=False)

		response = self.client.get(reverse('trade_list'))

		self.assertNotContains(response, 'PAPER')

	def test_trade_list_paper_pnl_rendered_in_yellow(self):
		day = _market_day()
		_make_trade(day, is_paper_trade=True, entry_price='5.00', exit_price='7.00')

		response = self.client.get(reverse('trade_list'))

		# Yellow colour applied to paper P&L, not the standard pnl_color class
		self.assertContains(response, '#fbbf24')

	def test_trade_list_real_pnl_not_rendered_in_yellow(self):
		day = _market_day()
		_make_trade(day, is_paper_trade=False, entry_price='5.00', exit_price='7.00')

		response = self.client.get(reverse('trade_list'))

		# Real profit P&L uses text-profit class, not inline yellow style
		self.assertContains(response, 'text-profit')
		self.assertNotContains(response, 'style="color:#fbbf24"')


class PaperTradeDetailTests(TestCase):
	"""Trade detail page shows PAPER TRADE badge for paper trades."""

	def test_trade_detail_shows_paper_trade_badge(self):
		day = _market_day()
		trade = _make_trade(day, is_paper_trade=True)

		response = self.client.get(reverse('trade_detail', args=[trade.pk]))

		self.assertContains(response, 'PAPER TRADE')

	def test_trade_detail_no_paper_badge_for_real_trade(self):
		day = _market_day()
		trade = _make_trade(day, is_paper_trade=False)

		response = self.client.get(reverse('trade_detail', args=[trade.pk]))

		self.assertNotContains(response, 'PAPER TRADE')

	def test_trade_form_checkbox_present(self):
		response = self.client.get(reverse('trade_add'))

		self.assertContains(response, 'is_paper_trade')
		self.assertContains(response, 'Paper trade')

	def test_trade_form_saves_paper_trade_flag(self):
		day = _market_day()
		response = self.client.post(reverse('trade_add'), {
			'trade_date': day.isoformat(),
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': day.isoformat(),
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
			'is_paper_trade': 'on',
		}, follow=True)

		trade = Trade.objects.get()
		self.assertTrue(trade.is_paper_trade)

	def test_trade_form_defaults_to_real_trade(self):
		day = _market_day()
		self.client.post(reverse('trade_add'), {
			'trade_date': day.isoformat(),
			'symbol': 'SPX',
			'option_type': OptionType.CALL,
			'trade_type': TradeType.LONG_CALL,
			'strike': '5000',
			'expiry': day.isoformat(),
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
		}, follow=True)

		trade = Trade.objects.get()
		self.assertFalse(trade.is_paper_trade)


# ---------------------------------------------------------------------------
# Regression tests: M2M trades on JournalEntry
# ---------------------------------------------------------------------------

def _make_simple_trade(date=None):
	date = date or _market_day()
	return Trade.objects.create(
		trade_date=date,
		symbol='SPX',
		option_type=OptionType.PUT,
		trade_type=TradeType.LONG_PUT,
		strike='5000',
		expiry=date,
		quantity=1,
		entry_price='5.00',
		entry_time='09:30',
		status=TradeStatus.OPEN,
	)


class JournalEntryTradesManyToManyTests(TestCase):
	"""JournalEntry.trade FK was replaced with trades M2M — verify the new behaviour."""

	def test_journal_entry_can_link_multiple_trades(self):
		t1 = _make_simple_trade()
		t2 = _make_simple_trade()
		entry = JournalEntry.objects.create(title='Multi', content='body', entry_type=EntryType.OBSERVATION)
		entry.trades.set([t1, t2])
		self.assertEqual(entry.trades.count(), 2)

	def test_journal_entry_with_no_trades_is_valid(self):
		entry = JournalEntry.objects.create(title='Solo', content='body', entry_type=EntryType.OBSERVATION)
		self.assertEqual(entry.trades.count(), 0)

	def test_reverse_relation_from_trade(self):
		trade = _make_simple_trade()
		entry = JournalEntry.objects.create(title='Linked', content='body', entry_type=EntryType.OBSERVATION)
		entry.trades.add(trade)
		self.assertIn(entry, trade.journal_entries.all())

	def test_journal_list_view_ok(self):
		entry = JournalEntry.objects.create(title='List test', content='body', entry_type=EntryType.OBSERVATION)
		t = _make_simple_trade()
		entry.trades.add(t)
		response = self.client.get(reverse('journal_list'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'List test')

	def test_journal_list_shows_trade_count_not_individual_links(self):
		entry = JournalEntry.objects.create(title='Count test', content='body', entry_type=EntryType.OBSERVATION)
		t1 = _make_simple_trade()
		t2 = _make_simple_trade()
		entry.trades.set([t1, t2])
		response = self.client.get(reverse('journal_list'))
		# Should show "2 linked trades" not individual trade strings
		self.assertContains(response, '2 linked trade')
		self.assertNotContains(response, 'Linked trade: SPX')

	def test_journal_form_save_creates_m2m(self):
		t = _make_simple_trade()
		response = self.client.post(reverse('journal_new'), {
			'title': 'Form M2M test',
			'entry_type': EntryType.OBSERVATION,
			'content': 'some content',
			'trades': [t.pk],
			'session': '',
		}, follow=True)
		self.assertEqual(response.status_code, 200)
		entry = JournalEntry.objects.get(title='Form M2M test')
		self.assertIn(t, entry.trades.all())

	def test_journal_form_save_multiple_trades(self):
		t1 = _make_simple_trade()
		t2 = _make_simple_trade()
		self.client.post(reverse('journal_new'), {
			'title': 'Two trades',
			'entry_type': EntryType.OBSERVATION,
			'content': 'content',
			'trades': [t1.pk, t2.pk],
			'session': '',
		})
		entry = JournalEntry.objects.get(title='Two trades')
		self.assertEqual(entry.trades.count(), 2)

	def test_dashboard_loads_without_trade_select_related_error(self):
		"""Regression: dashboard used select_related('trade') which no longer exists."""
		JournalEntry.objects.create(title='Dash entry', content='body', entry_type=EntryType.OBSERVATION)
		day = _market_day()
		with patch('journal.views.timezone.localdate', return_value=day):
			response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Regression tests: tag auto-capitalisation
# ---------------------------------------------------------------------------

class TagCapitalisationTests(TestCase):
	"""Tags should have only their first character uppercased; the rest preserved."""

	def _post_trade(self, strategy_tags='', rule_break_tags=''):
		day = _market_day()
		data = {
			'trade_date': day.isoformat(),
			'symbol': 'SPX',
			'option_type': OptionType.PUT,
			'trade_type': TradeType.LONG_PUT,
			'strike': '5000',
			'expiry': day.isoformat(),
			'quantity': 1,
			'entry_price': '5.00',
			'entry_time': '09:30',
			'status': TradeStatus.OPEN,
			'strategy_tags_text': strategy_tags,
			'rule_break_tags_text': rule_break_tags,
			'rule_review': RuleReview.BROKE if rule_break_tags else '',
		}
		if rule_break_tags:
			data['rule_break_notes'] = 'test note'
		self.client.post(reverse('trade_add'), data)
		return Trade.objects.order_by('-pk').first()

	def test_lowercase_strategy_tag_gets_first_letter_uppercased(self):
		trade = self._post_trade(strategy_tags='gap fill')
		self.assertIn('Gap fill', trade.strategy_tags)

	def test_allcaps_strategy_tag_preserved(self):
		trade = self._post_trade(strategy_tags='VWAP reclaim')
		self.assertIn('VWAP reclaim', trade.strategy_tags)

	def test_lowercase_rule_break_tag_gets_first_letter_uppercased(self):
		trade = self._post_trade(rule_break_tags='early entry')
		self.assertIn('Early entry', trade.rule_break_tags)

	def test_allcaps_rule_break_tag_preserved(self):
		trade = self._post_trade(rule_break_tags='FOMO')
		self.assertIn('FOMO', trade.rule_break_tags)

	def test_multiple_tags_each_capitalised(self):
		trade = self._post_trade(strategy_tags='gap fill, VWAP, momentum')
		self.assertIn('Gap fill', trade.strategy_tags)
		self.assertIn('VWAP', trade.strategy_tags)
		self.assertIn('Momentum', trade.strategy_tags)


# ---------------------------------------------------------------------------
# Regression tests: rule-break tag chips auto-populate from trades
# ---------------------------------------------------------------------------

class RuleBreakTagOptionsTemplateTagTests(TestCase):
	"""rule_break_tag_options should return tags from existing trades, not hardcoded defaults."""

	def test_no_hardcoded_defaults_when_no_trades_exist(self):
		from journal.templatetags.journal_extras import rule_break_tag_options
		# No trades in DB and empty preferences — should return empty (no hardcoded presets)
		prefs, _ = AppPreferences.objects.get_or_create(pk=1)
		prefs.rule_break_tag_templates = []
		prefs.save()
		result = rule_break_tag_options()
		self.assertEqual(result, [])

	def test_returns_tags_from_saved_trades(self):
		from journal.templatetags.journal_extras import rule_break_tag_options
		prefs, _ = AppPreferences.objects.get_or_create(pk=1)
		prefs.rule_break_tag_templates = []
		prefs.save()
		day = _market_day()
		Trade.objects.create(
			trade_date=day, symbol='SPX', option_type=OptionType.PUT,
			trade_type=TradeType.LONG_PUT, strike='5000', expiry=day,
			quantity=1, entry_price='5.00', entry_time='09:30', status=TradeStatus.OPEN,
			rule_break_tags=['Oversized', 'FOMO'],
		)
		result = rule_break_tag_options()
		self.assertIn('Oversized', result)
		self.assertIn('FOMO', result)

	def test_strategy_tag_options_returns_tags_from_saved_trades(self):
		from journal.templatetags.journal_extras import strategy_tag_options
		day = _market_day()
		Trade.objects.create(
			trade_date=day, symbol='SPX', option_type=OptionType.PUT,
			trade_type=TradeType.LONG_PUT, strike='5000', expiry=day,
			quantity=1, entry_price='5.00', entry_time='09:30', status=TradeStatus.OPEN,
			strategy_tags=['VWAP reclaim', 'Gap fill'],
		)
		result = strategy_tag_options()
		self.assertIn('VWAP reclaim', result)
		self.assertIn('Gap fill', result)


# ---------------------------------------------------------------------------
# Regression tests: journal new/edit redirects
# ---------------------------------------------------------------------------

class JournalRedirectTests(TestCase):
	"""After save, journal should redirect to the list, not a detail page."""

	def test_new_entry_redirects_to_list(self):
		response = self.client.post(reverse('journal_new'), {
			'title': 'Redirect test',
			'entry_type': EntryType.OBSERVATION,
			'content': 'body',
			'session': '',
		})
		self.assertRedirects(response, reverse('journal_list'))

	def test_edit_entry_redirects_to_list(self):
		entry = JournalEntry.objects.create(title='To edit', content='body', entry_type=EntryType.OBSERVATION)
		response = self.client.post(reverse('journal_edit', args=[entry.pk]), {
			'title': 'Edited',
			'entry_type': EntryType.OBSERVATION,
			'content': 'updated',
			'session': '',
		})
		self.assertRedirects(response, reverse('journal_list'))

	def test_journal_detail_url_does_not_exist(self):
		"""The /journal/<pk>/ detail endpoint was removed."""
		entry = JournalEntry.objects.create(title='X', content='y', entry_type=EntryType.OBSERVATION)
		response = self.client.get(f'/journal/{entry.pk}/')
		self.assertEqual(response.status_code, 404)

