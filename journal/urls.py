from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Trades
    path('trades/', views.trade_list, name='trade_list'),
    path('trades/add/', views.trade_add, name='trade_add'),
    path('trades/quick-add/', views.trade_quick_add, name='trade_quick_add'),
    path('trades/<int:pk>/', views.trade_detail, name='trade_detail'),
    path('trades/<int:pk>/edit/', views.trade_edit, name='trade_edit'),
    path('trades/<int:pk>/screenshot/delete/', views.trade_screenshot_delete, name='trade_screenshot_delete'),
    path('trades/<int:pk>/delete/', views.trade_delete, name='trade_delete'),
    path('trades/export/', views.trade_export, name='trade_export'),

    # Sessions
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/<str:date>/', views.session_detail, name='session_detail'),
    path('sessions/<str:date>/edit/', views.session_edit, name='session_edit'),
    path('sessions/<str:date>/checklist/<str:item_id>/toggle/', views.checklist_toggle, name='checklist_toggle'),

    # Calendar
    path('calendar/', views.calendar_view, name='calendar'),

    # Journal entries
    path('journal/', views.journal_list, name='journal_list'),
    path('journal/new/', views.journal_new, name='journal_new'),
    path('journal/<int:pk>/edit/', views.journal_edit, name='journal_edit'),
    path('journal/<int:pk>/delete/', views.journal_delete, name='journal_delete'),

    # Goals
    path('goals/', views.goals_list, name='goals'),
    path('goals/new/', views.goal_new, name='goal_new'),
    path('goals/<int:pk>/edit/', views.goal_edit, name='goal_edit'),
    path('goals/<int:pk>/delete/', views.goal_delete, name='goal_delete'),

    # Settings / checklist template editor
    path('settings/', views.settings_index, name='settings_index'),
    path('settings/checklist/', views.settings_checklist, name='settings_checklist'),
    path('settings/checklist/new/', views.checklist_template_new, name='checklist_template_new'),
    path('settings/checklist/<int:pk>/', views.checklist_template_edit, name='checklist_template_edit'),
    path('settings/checklist/<int:pk>/delete/', views.checklist_template_delete, name='checklist_template_delete'),
    path('settings/checklist/<int:pk>/activate/', views.checklist_template_activate, name='checklist_template_activate'),

    # CSV import
    path('import/', views.import_upload, name='import_upload'),
    path('import/preview/<str:filename>/', views.import_preview, name='import_preview'),
    path('import/confirm/<str:filename>/', views.import_confirm, name='import_confirm'),
]
