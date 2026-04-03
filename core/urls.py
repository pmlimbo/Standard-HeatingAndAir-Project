from django.urls import path
from . import views

urlpatterns = [
    path('', views.timesheet),

    path('add/', views.add_customer),

    path('reports/', views.reports),

    path('timesheet/', views.timesheet),

    path('export-timesheet/', views.export_timesheet),

    path('delete-entry/<int:entry_id>/', views.delete_entry),
]