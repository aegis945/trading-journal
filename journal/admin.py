from django.contrib import admin
from .models import (
    TradingSession, Trade, PreTradeChecklist,
    DailyRoutine, JournalEntry, PerformanceGoal, AppPreferences,
)


@admin.register(TradingSession)
class TradingSessionAdmin(admin.ModelAdmin):
    list_display  = ('date', 'market_bias', 'psychological_state', 'vix_level', 'total_pnl', 'trade_count')
    list_filter   = ('market_bias', 'psychological_state')
    search_fields = ('date', 'market_open_notes', 'session_notes', 'lessons_learned')
    date_hierarchy = 'date'
    ordering      = ('-date',)


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display  = (
        'trade_date', 'symbol', 'option_type', 'strike', 'expiry',
        'trade_type', 'quantity', 'entry_price', 'exit_price',
        'pnl', 'pnl_percent', 'risk_reward_ratio', 'status', 'imported',
    )
    list_filter   = ('status', 'trade_type', 'option_type', 'symbol', 'imported')
    search_fields = ('symbol', 'trade_notes', 'exit_notes', 'ibkr_trade_id')
    date_hierarchy = 'trade_date'
    ordering      = ('-trade_date', '-entry_time')
    readonly_fields = ('pnl', 'pnl_percent', 'risk_reward_ratio', 'created_at', 'updated_at')


@admin.register(PreTradeChecklist)
class PreTradeChecklistAdmin(admin.ModelAdmin):
    list_display  = ('name', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name',)


@admin.register(DailyRoutine)
class DailyRoutineAdmin(admin.ModelAdmin):
    list_display  = ('session', 'checklist_template', 'completion_percent', 'completed_at')
    list_filter   = ('checklist_template',)
    raw_id_fields = ('session',)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display  = ('title', 'entry_type', 'session', 'created_at')
    list_filter   = ('entry_type',)
    search_fields = ('title', 'content')
    raw_id_fields = ('session',)
    filter_horizontal = ('trades',)
    date_hierarchy = 'created_at'


@admin.register(PerformanceGoal)
class PerformanceGoalAdmin(admin.ModelAdmin):
    list_display  = ('title', 'metric', 'period', 'target_value', 'current_value', 'progress_percent', 'status')
    list_filter   = ('status', 'metric', 'period')
    search_fields = ('title', 'description')


@admin.register(AppPreferences)
class AppPreferencesAdmin(admin.ModelAdmin):
    list_display = ('display_currency', 'usd_to_eur_rate', 'updated_at')
