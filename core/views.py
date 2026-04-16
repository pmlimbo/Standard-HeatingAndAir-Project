import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomerForm
from .models import Employee, Job, TimeEntry, WorkCode


def is_authorized(user):
    return (
        user.is_superuser or
        user.is_staff or
        user.groups.filter(name='Authorized').exists()
    )


def parse_work_date(value):
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


@login_required
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('timesheet')
    else:
        form = CustomerForm()

    return render(request, 'core/add_customer.html', {'form': form})


@login_required
@user_passes_test(is_authorized, login_url='/')
def reports(request):
    return render(request, 'core/reports.html')


@login_required
def timesheet(request):
    jobs = Job.objects.all().order_by('job_number')
    workcodes = WorkCode.objects.filter(is_active=True, requires_job=True).order_by('code')
    non_job_codes = WorkCode.objects.filter(is_active=True, requires_job=False).order_by('code')
    hour_options = ["0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2", "3", "4", "5", "6", "7", "8"]
    drive_time_options = ["0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2"]

    selected_date_obj = parse_work_date(request.GET.get('date'))
    selected_date = selected_date_obj.isoformat()
    employee, _ = Employee.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        work_date_obj = parse_work_date(request.POST.get('date') or selected_date)
        indices = sorted({
            key.rsplit('_', 1)[1]
            for key in request.POST
            if key.startswith(('job_', 'work_code_', 'non_job_code_', 'hours_', 'drive_time_', 'mileage_', 'comments_'))
            and '_' in key
        })

        for index in indices:
            job_raw = (request.POST.get(f'job_{index}') or '').strip()
            wc_raw = (request.POST.get(f'work_code_{index}') or '').strip()
            non_job_code_val = (request.POST.get(f'non_job_code_{index}') or '').strip()
            hours = (request.POST.get(f'hours_{index}') or '').strip()
            drive_time = (request.POST.get(f'drive_time_{index}') or '').strip()
            mileage = (request.POST.get(f'mileage_{index}') or '').strip()
            comments = (request.POST.get(f'comments_{index}') or '').strip()

            if not any([job_raw, wc_raw, non_job_code_val, hours, drive_time, mileage, comments]):
                continue

            if not hours or not drive_time or mileage == "":
                continue

            job = None
            if job_raw:
                job_number = job_raw.split('|')[0].strip()
                job = Job.objects.filter(job_number=job_number).first()

            work_code = None
            if wc_raw:
                wc_code = wc_raw.split('-')[0].strip()
                work_code = WorkCode.objects.filter(code=wc_code).first()

            if non_job_code_val:
                if work_code is not None:
                    continue
                work_code = WorkCode.objects.filter(code=non_job_code_val).first()

            if not work_code:
                continue

            if work_code.requires_job and not job:
                continue

            try:
                hours_value = Decimal(hours)
                drive_time_value = Decimal(drive_time)
                mileage_value = Decimal(mileage)
            except InvalidOperation:
                continue

            TimeEntry.objects.create(
                employee=employee,
                job=job,
                work_code=work_code,
                work_date=work_date_obj,
                hours_worked=hours_value,
                drive_time=drive_time_value,
                mileage=mileage_value,
                comments=comments,
            )

        return redirect(f"/timesheet/?date={work_date_obj.isoformat()}")

    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=selected_date_obj
    ).select_related('job', 'work_code').order_by('id')

    total_hours = sum(entry.hours_worked for entry in entries)
    total_miles = sum(entry.mileage for entry in entries)

    return render(request, 'core/timesheet.html', {
        'jobs': jobs,
        'workcodes': workcodes,
        'non_job_codes': non_job_codes,
        'selected_date': selected_date,
        'hour_options': hour_options,
        'drive_time_options': drive_time_options,
        'entries': entries,
        'total_hours': total_hours,
        'total_miles': total_miles,
    })


@login_required
@require_POST
def delete_entry(request, entry_id):
    entry = get_object_or_404(TimeEntry, id=entry_id)

    if entry.employee.user != request.user:
        return redirect('timesheet')

    date_str = entry.work_date.strftime("%Y-%m-%d")
    entry.delete()
    return redirect(f'/timesheet/?date={date_str}')


@login_required
def export_timesheet(request):
    work_date = parse_work_date(request.GET.get('date'))
    employee, _ = Employee.objects.get_or_create(user=request.user)

    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=work_date
    ).select_related('job', 'work_code').order_by('id')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timesheet.csv"'
    writer = csv.writer(response)

    writer.writerow([
        'EntryDate', 'EmployeeCode', 'Employee_Name', 'WorkDate', 'DayOfWeek',
        'LineNumber', 'JobNumber', 'Job_Address', 'Job_Name', 'Work_Code',
        'Hours_Worked', 'Drive_Time', 'Mileage', 'Comments', 'Logfield'
    ])

    for i, entry in enumerate(entries, start=1):
        formatted_date = entry.work_date.strftime('%d-%b-%y')
        writer.writerow([
            formatted_date,
            request.user.username,
            f"{request.user.first_name} {request.user.last_name}".upper().strip(),
            formatted_date,
            entry.work_date.strftime('%A'),
            i,
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

    return response
