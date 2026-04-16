from django.contrib import admin

from .models import Customer, Employee, Job, TimeEntry, WorkCode


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email', 'phone')
    list_filter = ('created_at',)


@admin.register(WorkCode)
class WorkCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'description', 'requires_job', 'is_active')
    search_fields = ('code', 'description')
    list_filter = ('requires_job', 'is_active')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_number', 'job_name', 'street_address', 'city', 'state', 'zip_code')
    search_fields = ('job_number', 'job_name', 'street_address', 'city', 'state', 'zip_code')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'work_date', 'job', 'work_code', 'hours_worked', 'drive_time', 'mileage')
    search_fields = ('employee__user__username', 'job__job_number', 'work_code__code', 'comments')
    list_filter = ('work_date', 'work_code')
