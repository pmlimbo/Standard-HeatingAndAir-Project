from django.urls import path
from . import views

urlpatterns = [
    path('', views.timesheet, name='home'),
    path('add/', views.add_customer, name='add_customer'),
    path('lookup/jobs/', views.search_jobs, name='search_jobs'),
    path('lookup/work-codes/', views.search_work_codes, name='search_work_codes'),
    path('lookup/non-job-codes/', views.search_non_job_codes, name='search_non_job_codes'),
    path('lookup/employees/', views.search_employees, name='search_employees'),
    path('reports/', views.reports, name='reports'),
    path('reports/reference-data/<slug:dataset_key>/download/', views.download_reference_data, name='download_reference_data'),
    path('reports/reference-data/<slug:dataset_key>/upload/', views.upload_reference_data, name='upload_reference_data'),
    path('reports/export-jobs-list/', views.export_jobs_list, name='export_jobs_list'),
    path('timesheet/', views.timesheet, name='timesheet'),
    path('export-timesheet/', views.export_timesheet, name='export_timesheet'),
    path('delete-entry/<int:entry_id>/', views.delete_entry, name='delete_entry'),
]
