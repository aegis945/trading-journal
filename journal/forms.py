"""
journal/forms.py
"""
import json
from django import forms
from .models import (
    Trade, TradingSession, JournalEntry,
    PreTradeChecklist, PerformanceGoal,
    OptionType, TradeType, TradeStatus, MarketBias,
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
            'trade_notes':            forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'Pre-trade rationale…'}),
            'exit_notes':             forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '3', 'placeholder': 'What happened…'}),
            'ibkr_trade_id':          forms.TextInput(attrs={'class': _INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate the text field from the instance's JSON list
        if self.instance and self.instance.pk:
            self.fields['strategy_tags_text'].initial = ', '.join(self.instance.strategy_tags or [])

    def clean_strategy_tags_text(self):
        raw = self.cleaned_data.get('strategy_tags_text', '')
        return [t.strip() for t in raw.split(',') if t.strip()]

    def save(self, commit=True):
        trade = super().save(commit=False)
        trade.strategy_tags = self.cleaned_data['strategy_tags_text']
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
        fields = ['title', 'entry_type', 'content', 'trade', 'session']
        widgets = {
            'title':      forms.TextInput(attrs={'class': _INPUT_CLASSES, 'placeholder': 'Entry title'}),
            'entry_type': forms.Select(attrs={'class': _SELECT_CLASSES}),
            'content':    forms.Textarea(attrs={'id': 'journal-editor', 'class': _TEXTAREA_CLASSES, 'rows': '12'}),
            'trade':      forms.Select(attrs={'class': _SELECT_CLASSES}),
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
        fields = '__all__'
        widgets = {
            'title':         forms.TextInput(attrs={'class': _INPUT_CLASSES}),
            'description':   forms.Textarea(attrs={'class': _TEXTAREA_CLASSES, 'rows': '2'}),
            'metric':        forms.Select(attrs={'class': _SELECT_CLASSES}),
            'target_value':  forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01'}),
            'current_value': forms.NumberInput(attrs={'class': _INPUT_CLASSES, 'step': '0.01'}),
            'period':        forms.Select(attrs={'class': _SELECT_CLASSES}),
            'start_date':    forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'end_date':      forms.DateInput(attrs={'class': _INPUT_CLASSES, 'type': 'date'}),
            'status':        forms.Select(attrs={'class': _SELECT_CLASSES}),
        }
