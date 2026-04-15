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

    workcodes = WorkCode.objects.filter(
        is_active=True,
        requires_job=True
    ).order_by('code')

    non_job_codes = WorkCode.objects.filter(
        is_active=True,
        requires_job=False
    ).order_by('code')

    hour_options = ["0","0.25","0.5","0.75","1","1.25","1.5","2","3","4","5","6","7","8"]
    drive_time_options = ["0","0.25","0.5","0.75","1","1.25","1.5","2"]

    selected_date = request.GET.get('date') or date.today().isoformat()
    selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()

    employee, _ = Employee.objects.get_or_create(user=request.user)

    # ================= SAVE =================
    if request.method == 'POST':
        work_date = request.POST.get('date') or selected_date
        work_date_obj = datetime.strptime(work_date, "%Y-%m-%d").date()

        for key in request.POST:
            if key.startswith('job_'):

                index = key.split('_')[1]

                job_raw = request.POST.get(f'job_{index}')
                wc_raw = request.POST.get(f'work_code_{index}')
                non_job_code_val = request.POST.get(f'non_job_code_{index}')

                hours = request.POST.get(f'hours_{index}')
                drive_time = request.POST.get(f'drive_time_{index}')
                mileage = request.POST.get(f'mileage_{index}')
                comments = request.POST.get(f'comments_{index}')

                # Skip empty rows
                if not any([job_raw, wc_raw, non_job_code_val, hours, drive_time, mileage]):
                    continue

                # Required
                if not hours or not drive_time or mileage == "":
                    continue

                # ===== JOB PARSE =====
                job = None
                if job_raw:
                    try:
                        job_number = job_raw.split('|')[0].strip()
                        job = Job.objects.filter(job_number=job_number).first()
                    except:
                        job = None

                # ===== WORK CODE PARSE =====
                work_code = None

                if wc_raw:
                    try:
                        wc_code = wc_raw.split('-')[0].strip()
                        work_code = WorkCode.objects.filter(code=wc_code).first()
                    except:
                        work_code = None

                if non_job_code_val:
                    work_code = WorkCode.objects.filter(code=non_job_code_val).first()

                # Validation
                if wc_raw and non_job_code_val:
                    continue

                if not work_code:
                    continue

                if work_code.requires_job and not job:
                    continue

                # SAVE
                TimeEntry.objects.create(
                    employee=employee,
                    job=job,
                    work_code=work_code,
                    work_date=work_date_obj,
                    hours_worked=float(hours),
                    drive_time=float(drive_time),
                    mileage=float(mileage),
                    comments=comments,
                )

        return redirect(f'/timesheet/?date={work_date}')

    # ================= LOAD EXISTING =================
    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=selected_date_obj
    ).select_related('job', 'work_code').order_by('id')

    # 🔥 RESTORED TOTALS
    total_hours = sum(e.hours_worked for e in entries)
    total_miles = sum(e.mileage for e in entries)

    return render(request, 'core/timesheet.html', {
        'jobs': jobs,
        'workcodes': workcodes,
        'non_job_codes': non_job_codes,
        'selected_date': selected_date,
        'hour_options': hour_options,
        'drive_time_options': drive_time_options,
        'entries': entries,
        'total_hours': total_hours,
        'total_miles': total_miles
    })

# ================= DELETE =================
@login_required
def delete_entry(request, entry_id):
    entry = TimeEntry.objects.get(id=entry_id)

    if entry.employee.user != request.user:
        return redirect('/timesheet/')

    date_str = entry.work_date.strftime("%Y-%m-%d")
    entry.delete()

    return redirect(f'/timesheet/?date={date_str}')


# ================= EXPORT =================
@login_required
def export_timesheet(request):
    work_date = request.GET.get('date')

    if work_date:
        try:
            work_date = datetime.strptime(work_date, "%Y-%m-%d").date()
        except:
            work_date = date.today()
    else:
        work_date = date.today()

    employee, _ = Employee.objects.get_or_create(user=request.user)

    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=work_date
    ).select_related('job', 'work_code').order_by('id')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timesheet.csv"'

    writer = csv.writer(response)

    writer.writerow([
        'EntryDate','EmployeeCode','Employee_Name','WorkDate','DayOfWeek',
        'LineNumber','JobNumber','Job_Address','Job_Name','Work_Code',
        'Hours_Worked','Drive_Time','Mileage','Comments','Logfield'
    ])

    for i, entry in enumerate(entries, start=1):
        formatted_date = entry.work_date.strftime('%d-%b-%y')

        writer.writerow([
            formatted_date,
            request.user.username,
            f"{request.user.first_name} {request.user.last_name}".upper(),
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