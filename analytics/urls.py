from django.urls import path
from . import views

urlpatterns = [
    path('', views.analytics_index, name='analytics'),
    path('review/', views.performance_review, name='performance_review'),

    # JSON endpoints for Chart.js
    path('data/win-rate-by-tag/', views.data_win_rate_by_tag, name='data_win_rate_by_tag'),
    path('data/pnl-by-time/', views.data_pnl_by_time, name='data_pnl_by_time'),
    path('data/pnl-by-weekday/', views.data_pnl_by_weekday, name='data_pnl_by_weekday'),
    path('data/psych-vs-outcome/', views.data_psych_vs_outcome, name='data_psych_vs_outcome'),
    path('data/delta-vs-pnl/', views.data_delta_vs_pnl, name='data_delta_vs_pnl'),
    path('data/streak/', views.data_streak, name='data_streak'),
    path('data/drawdown/', views.data_drawdown, name='data_drawdown'),
    path('data/setup-quality/', views.data_setup_quality, name='data_setup_quality'),
    path('data/rule-review-summary/', views.data_rule_review_summary, name='data_rule_review_summary'),
    path('data/rule-break-tags/', views.data_rule_break_tags, name='data_rule_break_tags'),
    path('data/duration-vs-pnl/', views.data_duration_vs_pnl, name='data_duration_vs_pnl'),
    path('data/monthly-table/', views.data_monthly_table, name='data_monthly_table'),
]
