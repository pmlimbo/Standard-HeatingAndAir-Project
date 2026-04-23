from django.urls import path
from . import views

urlpatterns = [
    path('', views.timesheet, name='home'),
    path('add/', views.add_customer, name='add_customer'),
    path('reports/', views.reports, name='reports'),
    path('reports/export-jobs-list/', views.export_jobs_list, name='export_jobs_list'),
    path('timesheet/', views.timesheet, name='timesheet'),
    path('export-timesheet/', views.export_timesheet, name='export_timesheet'),
    path('delete-entry/<int:entry_id>/', views.delete_entry, name='delete_entry'),
]
