from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test

from datetime import date, datetime
import csv

from .forms import CustomerForm
from .models import Customer, WorkCode, Job, Employee, TimeEntry


# ================= AUTH =================
def is_authorized(user):
    return (
        user.is_superuser or
        user.is_staff or
        user.groups.filter(name='Authorized').exists()
    )


# ================= HOME =================
@login_required
def home(request):
    customers = Customer.objects.all().order_by('-created_at')
    workcodes = WorkCode.objects.all().order_by('code')

    return render(request, 'core/home.html', {
        'customers': customers,
        'workcodes': workcodes
    })


# ================= ADD CUSTOMER =================
@login_required
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/')
    else:
        form = CustomerForm()

    return render(request, 'core/add_customer.html', {'form': form})


# ================= REPORTS =================
@login_required
@user_passes_test(is_authorized, login_url='/')
def reports(request):
    return render(request, 'core/reports.html')


# ================= TIMESHEET =================
@login_required
def timesheet(request):
    jobs = Job.objects.all().order_by('job_number')

    hour_options = [
        "0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2", "3", "4", "5", "6", "7", "8"
    ]

    drive_time_options = [
        "0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2"
    ]

    workcodes = WorkCode.objects.filter(
        is_active=True,
        requires_job=True
    ).order_by('code')

    non_job_codes = WorkCode.objects.filter(
        is_active=True,
        requires_job=False
    ).order_by('code')

    selected_date = request.GET.get('date') or date.today().isoformat()

    if request.method == 'POST':
        work_date = request.POST.get('work_date')

        # FIX: never allow blank date
        if not work_date:
            work_date = date.today().isoformat()

        employee = Employee.objects.get(user=request.user)

        for key in request.POST:
            if key.startswith('job_'):

                index = key.split('_')[1]

                job_id = request.POST.get(f'job_{index}')
                work_code_id = request.POST.get(f'work_code_{index}')
                non_job_code_id = request.POST.get(f'non_job_code_{index}')
                hours = request.POST.get(f'hours_{index}')
                drive_time = request.POST.get(f'drive_time_{index}')
                mileage = request.POST.get(f'mileage_{index}')
                comments = request.POST.get(f'comments_{index}')

                # Skip completely empty rows
                if not any([job_id, work_code_id, non_job_code_id, hours, drive_time, mileage]):
                    continue

                # Required fields
                if not hours or not drive_time or mileage == "":
                    continue

                # Must choose ONE code
                if work_code_id and non_job_code_id:
                    continue

                if not work_code_id and not non_job_code_id:
                    continue

                # If work code requires job
                if work_code_id and not job_id:
                    continue

                TimeEntry.objects.create(
                    employee=employee,
                    job_id=job_id if job_id else None,
                    work_code_id=work_code_id or non_job_code_id,
                    work_date=work_date,
                    hours_worked=hours,
                    drive_time=drive_time,
                    mileage=mileage,
                    comments=comments,
                )

        return redirect('/timesheet/')

    return render(request, 'core/timesheet.html', {
        'jobs': jobs,
        'workcodes': workcodes,
        'non_job_codes': non_job_codes,
        'selected_date': selected_date,
        'hour_options': hour_options,
        'drive_time_options': drive_time_options
    })


# ================= EXPORT =================
@login_required
def export_timesheet(request):
    work_date = request.GET.get('date')

    # FIX: prevent crash if blank
    if work_date:
        try:
            work_date = datetime.strptime(work_date, "%Y-%m-%d").date()
        except:
            work_date = date.today()
    else:
        work_date = date.today()

    employee = Employee.objects.get(user=request.user)

    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=work_date
    ).select_related('job', 'work_code').order_by('id')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timesheet.csv"'

    writer = csv.writer(response)

    writer.writerow([
        'EntryDate',
        'EmployeeCode',
        'Employee_Name',
        'WorkDate',
        'DayOfWeek',
        'LineNumber',
        'JobNumber',
        'Job_Address',
        'Job_Name',
        'Work_Code',
        'Hours_Worked',
        'Drive_Time',
        'Mileage',
        'Comments',
        'Logfield'
    ])

    line_number = 1

    for entry in entries:
        formatted_date = entry.work_date.strftime('%d-%b-%y')
        day_of_week = entry.work_date.strftime('%A')

        writer.writerow([
            formatted_date,
            request.user.username,
            f"{request.user.first_name} {request.user.last_name}".upper(),
            formatted_date,
            day_of_week,
            line_number,
            entry.job.job_number if entry.job else '',
            entry.job.street_address if entry.job else '',
            entry.job.job_name if entry.job else '',
            entry.work_code.code,
            entry.hours_worked,
            entry.drive_time,
            entry.mileage,
            entry.comments,
            ''
        ])

        line_number += 1

    return response