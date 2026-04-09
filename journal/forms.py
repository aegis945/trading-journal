"""
journal/forms.py
"""
import json
from decimal import Decimal
from django import forms
from .models import (
    Trade, TradingSession, JournalEntry,
    PreTradeChecklist, PerformanceGoal, AppPreferences,
    OptionType, ProcessMetric, TradeType, TradeStatus, MarketBias, RuleReview, is_market_closed_day,
)


_INPUT_CLASSES  = 'w-full bg-[#1e263a] border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent'
_SELECT_CLASSES = 'w-full bg-[#1e263a] border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent'
_TEXTAREA_CLASSES = 'w-full bg-[#1e263a] border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent'


class TradeForm(forms.ModelForm):
    # strategy_tags rendered as comma-separated text
    strategy_tags_text = forms.CharField(
        required=False,
        label='Strategy Tags',
        help_text='Comma-separated, e.g. momentum, VWAP reclaim',
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLASSES,
            'placeholder': 'momentum, open drive, VWAP reclaim',
        }),
    )
    rule_break_tags_text = forms.CharField(
        required=False,
        label='Rule-break tags',
        help_text='Comma-separated, e.g. early entry, oversized, revenge trade',
        widget=forms.TextInput(attrs={
            'class': _INPUT_CLASSES,
            'placeholder': 'early entry, oversized, revenge trade',
        }),
    )

    class Meta:
        model  = Trade
        exclude = ['pnl', 'pnl_percent', 'risk_reward_ratio', 'strategy_tags',
                   'imported', 'created_at', 'updated_at']
        widgets = {
            'session':                forms.Select(attrs={'class': _SELECT_CLASSES}),
            'trade_date':             forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'symbol':                 forms.TextInput(attrs={'class': _INPUT_CLASSES, 'placeholder': 'SPX'}),
            'option_type':            forms.Select(attrs={'class': _SELECT_CLASSES}),
            'strike':                 forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.5', 'placeholder': '5000'}),
            'expiry':                 forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'quantity':               forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'placeholder': '1'}),
            'entry_price':            forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'placeholder': '5.50', 'x-model': 'entryPrice'}),
            'exit_price':             forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'placeholder': '8.00', 'x-model': 'exitPrice'}),
            'entry_time':             forms.TimeInput(attrs={'class': _INPUT_CLASSES, 'type': 'time'}),
            'exit_time':              forms.TimeInput(attrs={'class': _INPUT_CLASSES, 'type': 'time'}),
            'trade_type':             forms.Select(attrs={'class': _SELECT_CLASSES}),
            'status':                 forms.Select(attrs={'class': _SELECT_CLASSES}),
            'delta_entry':            forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.0001', 'placeholder': '0.3500'}),
            'theta_entry':            forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.0001', 'placeholder': '-12.0000'}),
            'vega_entry':             forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.0001'}),
            'iv_entry':               forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.0001', 'placeholder': '0.2500'}),
            'planned_stop_loss':      forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'x-model': 'stopLoss'}),
            'planned_take_profit_1':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'x-model': 'tp1'}),
            'planned_take_profit_2':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01'}),
            'planned_take_profit_3':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01'}),
            'setup_quality':          forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'min': '1', 'max': '5', 'placeholder': '3'}),
            'rule_review':            forms.Select(attrs={'class': _SELECT_CLASSES}),
            'rule_break_notes':       forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'What rule broke down? What triggered it?'}),
            'trade_notes':            forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'Pre-trade rationale…'}),
            'exit_notes':             forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'What happened…'}),
            'ta_screenshot':          forms.ClearableFileInput(attrs={'class': _INPUT_CLASSES, 'accept': 'image/*'}),
            'ibkr_trade_id':          forms.TextInput(attrs={'class': _INPUT_CLASSES}),
            'is_paper_trade':         forms.CheckboxInput(attrs={'class': 'rounded'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate the text field from the instance's JSON list
        if self.instance and self.instance.pk:
            self.fields['strategy_tags_text'].initial = ', '.join(self.instance.strategy_tags or [])
            self.fields['rule_break_tags_text'].initial = ', '.join(self.instance.rule_break_tags or [])
        elif not self.is_bound and self.initial.get('quantity') in (None, ''):
            self.fields['quantity'].initial = 1
        self.fields['rule_review'].required = False
        self.fields['rule_review'].choices = [('', 'Not reviewed')] + list(RuleReview.choices)

    def clean_strategy_tags_text(self):
        raw = self.cleaned_data.get('strategy_tags_text', '')
        return [t.strip()[:1].upper() + t.strip()[1:] for t in raw.split(',') if t.strip()]

    def clean_rule_break_tags_text(self):
        raw = self.cleaned_data.get('rule_break_tags_text', '')
        return [tag.strip()[:1].upper() + tag.strip()[1:] for tag in raw.split(',') if tag.strip()]

    def clean_trade_date(self):
        trade_date = self.cleaned_data['trade_date']
        if is_market_closed_day(trade_date):
            raise forms.ValidationError('Trades cannot be logged when the market is closed.')
        return trade_date

    def clean(self):
        cleaned_data = super().clean()
        rule_review = cleaned_data.get('rule_review')
        rule_break_tags = cleaned_data.get('rule_break_tags_text') or []
        rule_break_notes = (cleaned_data.get('rule_break_notes') or '').strip()

        if rule_review != RuleReview.BROKE:
            cleaned_data['rule_break_tags_text'] = []
            cleaned_data['rule_break_notes'] = ''
        elif not rule_break_tags and not rule_break_notes:
            self.add_error('rule_break_tags_text', 'Add at least one rule-break tag or note for rule-break trades.')

        return cleaned_data

    def save(self, commit=True):
        trade = super().save(commit=False)
        trade.strategy_tags = self.cleaned_data['strategy_tags_text']
        trade.rule_break_tags = self.cleaned_data['rule_break_tags_text']
        if commit:
            trade.save()
        return trade


class TradingSessionForm(forms.ModelForm):
    class Meta:
        model  = TradingSession
        fields = [
            'market_bias', 'psychological_state', 'psychological_notes',
            'vix_level', 'market_open_notes', 'session_notes', 'lessons_learned',
        ]
        widgets = {
            'market_bias':          forms.Select(attrs={'class': _SELECT_CLASSES}),
            'psychological_state':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'min': '1', 'max': '5'}),
            'psychological_notes':  forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '2'}),
            'vix_level':            forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'placeholder': '18.5'}),
            'market_open_notes':    forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3'}),
            'session_notes':        forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3'}),
            'lessons_learned':      forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['market_bias'].choices = [('', 'Select market bias')] + list(MarketBias.choices)
        self.fields['psychological_state'].required = False
        self.fields['psychological_state'].widget.attrs['placeholder'] = 'Rate 1-5'
        self.fields['psychological_notes'].widget.attrs['placeholder'] = 'How are you showing up today?'
        self.fields['market_open_notes'].widget.attrs['placeholder'] = 'What matters most before the open?'
        self.fields['session_notes'].widget.attrs['placeholder'] = 'What stood out after the session?'
        self.fields['lessons_learned'].widget.attrs['placeholder'] = 'What will you repeat or change next time?'


class JournalEntryForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False, label='Tags',
        help_text='Comma-separated',
        widget=forms.TextInput(attrs={'class': _INPUT_CLASSES, 'placeholder': 'discipline, loss, setup'}),
    )

    class Meta:
        model  = JournalEntry
        fields = ['title', 'entry_type', 'content', 'trades', 'session']
        widgets = {
            'title':      forms.TextInput(attrs={'class': _INPUT_CLASSES, 'placeholder': 'Entry title'}),
            'entry_type': forms.Select(attrs={'class': _SELECT_CLASSES}),
            'content':    forms.Textarea(attrs={'id': 'journal-editor', 'class': _TEXTAREA_CLASSES, 'rows': '12'}),
            'trades':     forms.SelectMultiple(attrs={'class': _SELECT_CLASSES, 'size': '4'}),
            'session':    forms.Select(attrs={'class': _SELECT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['tags_text'].initial = ', '.join(self.instance.tags or [])

    def clean_tags_text(self):
        raw = self.cleaned_data.get('tags_text', '')
        return [t.strip() for t in raw.split(',') if t.strip()]

    def save(self, commit=True):
        entry = super().save(commit=False)
        entry.tags = self.cleaned_data['tags_text']
        if commit:
            entry.save()
            self.save_m2m()
        return entry


class PreTradeChecklistForm(forms.ModelForm):
    class Meta:
        model  = PreTradeChecklist
        fields = ['name', 'items', 'is_active']
        widgets = {
            'name':      forms.TextInput(attrs={'class': _INPUT_CLASSES}),
            'items':     forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '10',
                                               'placeholder': '[{"id": "1", "label": "Check VIX", "category": "Market Context"}]'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-accent bg-[#1e263a] border-white/10 rounded'}),
        }


class PerformanceGoalForm(forms.ModelForm):
    class Meta:
        model  = PerformanceGoal
        fields = [
            'title', 'description', 'process_metric', 'metric', 'target_value', 'current_value',
            'period', 'start_date', 'end_date', 'status',
        ]
        widgets = {
            'title':         forms.TextInput(attrs={'class': _INPUT_CLASSES, 'placeholder': 'Follow the rules'}),
            'description':   forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'Describe what success looks like for this goal.'}),
            'process_metric': forms.Select(attrs={'class': _SELECT_CLASSES}),
            'metric':        forms.Select(attrs={'class': _SELECT_CLASSES}),
            'target_value':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'placeholder': 'Optional for process goals'}),
            'current_value': forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01', 'placeholder': 'Optional for process goals'}),
            'period':        forms.Select(attrs={'class': _SELECT_CLASSES}),
            'start_date':    forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'end_date':      forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'status':        forms.Select(attrs={'class': _SELECT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['process_metric'].required = False
        self.fields['metric'].required = False
        self.fields['target_value'].required = False
        self.fields['current_value'].required = False
        self.fields['end_date'].required = False
        self.fields['process_metric'].choices = [('', 'Simple process goal (no automatic tracking)')] + list(ProcessMetric.choices)
        self.fields['process_metric'].help_text = 'Use this when the app should score the goal automatically from your trades and sessions.'
        self.fields['metric'].choices = [('', 'Process goal (no metric)')] + list(self.fields['metric'].choices)
        self.fields['metric'].help_text = 'Leave blank for goals like "Follow the rules" or "Stay patient".'
        self.fields['target_value'].help_text = 'Optional target. For process tracking, use a percentage target like 85 or 90.'
        self.fields['current_value'].help_text = 'Used only for manual measurable goals. Process-tracked goals calculate this automatically.'
        self.fields['end_date'].help_text = 'Optional. Leave blank for open-ended goals.'
        self.fields['title'].label = 'Goal'

    def clean(self):
        cleaned_data = super().clean()
        process_metric = cleaned_data.get('process_metric')
        metric = cleaned_data.get('metric')
        target_value = cleaned_data.get('target_value')
        current_value = cleaned_data.get('current_value')

        if process_metric and metric:
            self.add_error('process_metric', 'Choose either process tracking or a measurable metric, not both.')
            self.add_error('metric', 'Choose either a measurable metric or process tracking, not both.')

        if process_metric and target_value is not None and not (Decimal('0') < target_value <= Decimal('100')):
            self.add_error('target_value', 'Process-tracked goals use percentage targets between 0 and 100.')

        if metric and target_value is None:
            self.add_error('target_value', 'Set a target for measurable goals.')

        if process_metric:
            cleaned_data['metric'] = None
            cleaned_data['current_value'] = None
        elif not metric:
            cleaned_data['target_value'] = None
            cleaned_data['current_value'] = None
        elif target_value is None and current_value is not None:
            self.add_error('target_value', 'Add a target before tracking current progress.')

        return cleaned_data


class AppPreferencesForm(forms.ModelForm):
    class Meta:
        model = AppPreferences
        fields = ['display_currency']
        widgets = {
            'display_currency': forms.Select(attrs={
                'class': f'{_SELECT_CLASSES} h-[42px]',
                'style': 'background:var(--bg-elevated);',
            }),
        }


class RuleBreakSettingsForm(forms.ModelForm):
    rule_break_tag_templates_text = forms.CharField(
        required=False,
        label='Preset rule-break tags',
        help_text='One tag per line. These show up as quick-pick chips in trade entry.',
        widget=forms.Textarea(attrs={
            'class': _TEXTAREA_CLASSES,
            'rows': '6',
            'placeholder': 'early entry\noversized\nrevenge trade',
        }),
    )

    class Meta:
        model = AppPreferences
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance') or self.instance
        if instance:
            self.fields['rule_break_tag_templates_text'].initial = '\n'.join(instance.normalized_rule_break_tag_templates)

    def clean_rule_break_tag_templates_text(self):
        raw = self.cleaned_data.get('rule_break_tag_templates_text', '')
        tags = []
        seen = set()
        for chunk in raw.replace(',', '\n').splitlines():
            tag = chunk.strip()
            if not tag:
                continue
            lowered = tag.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            tags.append(tag)
        return tags

    def save(self, commit=True):
        preferences = self.instance
        preferences.rule_break_tag_templates = self.cleaned_data['rule_break_tag_templates_text']
        if commit:
            preferences.save()
        return preferences
