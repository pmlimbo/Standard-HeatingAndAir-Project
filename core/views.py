import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomerForm
from .models import Employee, Job, TimeEntry, WorkCode

TIME_ENTRY_FIELD_PREFIXES = (
    'job_',
    'work_code_',
    'non_job_code_',
    'hours_',
    'drive_time_',
    'mileage_',
    'comments_',
)

TIMESHEET_EXPORT_HEADERS = [
    'EntryDate', 'EmployeeCode', 'Employee_Name', 'WorkDate', 'DayOfWeek',
    'LineNumber', 'JobNumber', 'Job_Address', 'Job_Name', 'Work_Code',
    'Hours_Worked', 'Drive_Time', 'Mileage', 'Comments', 'Logfield',
]


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


def format_decimal_for_input(value):
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def format_job_label(job):
    return f"{job.job_number} | {job.job_name} | {job.street_address}"


def format_work_code_label(work_code):
    return f"{work_code.code} - {work_code.description}"


def get_entry_indices(data):
    return sorted({
        key.rsplit('_', 1)[1]
        for key in data
        if key.startswith(TIME_ENTRY_FIELD_PREFIXES) and '_' in key
    }, key=int)


def get_empty_form_values():
    return {
        'job': '',
        'work_code': '',
        'non_job_code': '',
        'hours': '',
        'drive_time': '0',
        'mileage': '',
        'comments': '',
    }


def get_submitted_form_values(data, index):
    return {
        'job': (data.get(f'job_{index}') or '').strip(),
        'work_code': (data.get(f'work_code_{index}') or '').strip(),
        'non_job_code': (data.get(f'non_job_code_{index}') or '').strip(),
        'hours': (data.get(f'hours_{index}') or '').strip(),
        'drive_time': (data.get(f'drive_time_{index}') or '').strip(),
        'mileage': (data.get(f'mileage_{index}') or '').strip(),
        'comments': (data.get(f'comments_{index}') or '').strip(),
    }


def row_has_meaningful_input(values):
    return any([
        values['job'],
        values['work_code'],
        values['non_job_code'],
        values['mileage'],
        values['comments'],
        values['hours'] not in ('', '0'),
        values['drive_time'] not in ('', '0'),
    ])


def validate_time_entry_values(values, *, force_validation=False):
    errors = []
    is_active = force_validation or row_has_meaningful_input(values)

    if not is_active:
        return None, [], False

    if values['work_code'] and values['non_job_code']:
        errors.append('Choose either a Work Code or a Non Job Code.')

    if not values['work_code'] and not values['non_job_code']:
        errors.append('Work Code or Non Job Code is required.')

    if values['work_code'] and not values['job']:
        errors.append('Job Number is required when using a Work Code.')

    job = None
    if values['job']:
        job_number = values['job'].split('|')[0].strip()
        job = Job.objects.filter(job_number=job_number).first()
        if not job:
            errors.append('Select a valid Job Number.')

    work_code = None
    if values['work_code']:
        work_code_value = values['work_code'].split('-')[0].strip()
        work_code = WorkCode.objects.filter(
            code=work_code_value,
            is_active=True,
            requires_job=True,
        ).first()
        if not work_code:
            errors.append('Select a valid Work Code.')
    elif values['non_job_code']:
        work_code = WorkCode.objects.filter(
            code=values['non_job_code'],
            is_active=True,
            requires_job=False,
        ).first()
        if not work_code:
            errors.append('Select a valid Non Job Code.')

    hours_value = None
    if values['hours'] == '':
        errors.append('Hours is required.')
    else:
        try:
            hours_value = Decimal(values['hours'])
            if hours_value <= 0:
                errors.append('Hours must be greater than 0.')
        except InvalidOperation:
            errors.append('Hours must be a valid number.')

    drive_time_value = None
    if values['drive_time'] == '':
        errors.append('Drive Time is required.')
    else:
        try:
            drive_time_value = Decimal(values['drive_time'])
        except InvalidOperation:
            errors.append('Drive Time must be a valid number.')

    mileage_value = Decimal('0')
    if values['mileage'] != '':
        try:
            mileage_value = Decimal(values['mileage'])
        except InvalidOperation:
            errors.append('Miles must be a valid number.')

    if errors:
        return None, errors, True

    return {
        'job': job,
        'work_code': work_code,
        'hours_worked': hours_value,
        'drive_time': drive_time_value,
        'mileage': mileage_value,
        'comments': values['comments'],
    }, [], True


def get_form_values(entry=None):
    if not entry:
        return get_empty_form_values()

    return {
        'job': format_job_label(entry.job) if entry.job else '',
        'work_code': format_work_code_label(entry.work_code) if entry.work_code.requires_job else '',
        'non_job_code': entry.work_code.code if not entry.work_code.requires_job else '',
        'hours': format_decimal_for_input(entry.hours_worked),
        'drive_time': format_decimal_for_input(entry.drive_time),
        'mileage': format_decimal_for_input(entry.mileage),
        'comments': entry.comments,
    }


def build_form_row(index, values=None, errors=None, title=None):
    return {
        'index': str(index),
        'title': title or f'Entry {index}',
        'values': values or get_empty_form_values(),
        'errors': errors or [],
    }


def get_timesheet_entries(employee, work_date):
    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=work_date,
    ).select_related('job', 'work_code').order_by('id')
    total_hours = sum(entry.hours_worked for entry in entries)
    total_miles = sum(entry.mileage for entry in entries)
    return entries, total_hours, total_miles


def build_timesheet_context(
    *,
    jobs,
    workcodes,
    non_job_codes,
    selected_date,
    hour_options,
    drive_time_options,
    entries,
    total_hours,
    total_miles,
    editing_entry=None,
    form_rows=None,
    submission_errors=None,
):
    if form_rows is None:
        if editing_entry:
            form_rows = [build_form_row('1', get_form_values(editing_entry), title='Edit Entry')]
        else:
            form_rows = [build_form_row('1', get_empty_form_values())]

    next_index = max((int(row['index']) for row in form_rows), default=1) + 1

    return {
        'jobs': jobs,
        'workcodes': workcodes,
        'non_job_codes': non_job_codes,
        'selected_date': selected_date,
        'hour_options': hour_options,
        'drive_time_options': drive_time_options,
        'entries': entries,
        'total_hours': total_hours,
        'total_miles': total_miles,
        'editing_entry': editing_entry,
        'form_rows': form_rows,
        'submission_errors': submission_errors or [],
        'next_index': next_index,
    }


def build_export_response(entries, filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    writer.writerow(TIMESHEET_EXPORT_HEADERS)

    for line_number, entry in enumerate(entries, start=1):
        employee_user = entry.employee.user
        employee_name = f"{employee_user.first_name} {employee_user.last_name}".strip() or employee_user.username
        formatted_date = entry.work_date.strftime('%d-%b-%y')
        writer.writerow([
            formatted_date,
            employee_user.username,
            employee_name.upper(),
            formatted_date,
            entry.work_date.strftime('%A'),
            line_number,
            entry.job.job_number if entry.job else '',
            entry.job.street_address if entry.job else '',
            entry.job.job_name if entry.job else '',
            entry.work_code.code,
            entry.hours_worked,
            entry.drive_time,
            entry.mileage,
            entry.comments,
            '',
        ])

    return response


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
    employees = Employee.objects.select_related('user').order_by(
        'user__last_name', 'user__first_name', 'user__username'
    )
    today = date.today().isoformat()
    return render(request, 'core/reports.html', {
        'employees': employees,
        'today': today,
    })


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
    editing_entry_id = request.POST.get('editing_entry_id') if request.method == 'POST' else request.GET.get('edit')
    editing_entry = None

    if editing_entry_id:
        editing_entry = TimeEntry.objects.filter(
            id=editing_entry_id,
            employee=employee,
        ).select_related('job', 'work_code').first()
        if request.method == 'GET' and editing_entry:
            selected_date_obj = editing_entry.work_date
            selected_date = selected_date_obj.isoformat()

    if request.method == 'POST':
        work_date_obj = parse_work_date(request.POST.get('date') or selected_date)
        if request.POST.get('editing_entry_id'):
            if not editing_entry:
                return redirect(f"/timesheet/?date={work_date_obj.isoformat()}")

            values = get_submitted_form_values(request.POST, '1')
            entry_data, errors, _ = validate_time_entry_values(values, force_validation=True)
            if errors:
                entries, total_hours, total_miles = get_timesheet_entries(employee, work_date_obj)
                context = build_timesheet_context(
                    jobs=jobs,
                    workcodes=workcodes,
                    non_job_codes=non_job_codes,
                    selected_date=work_date_obj.isoformat(),
                    hour_options=hour_options,
                    drive_time_options=drive_time_options,
                    entries=entries,
                    total_hours=total_hours,
                    total_miles=total_miles,
                    editing_entry=editing_entry,
                    form_rows=[build_form_row('1', values, errors=errors, title='Edit Entry')],
                    submission_errors=errors,
                )
                return render(request, 'core/timesheet.html', context)

            editing_entry.job = entry_data['job']
            editing_entry.work_code = entry_data['work_code']
            editing_entry.work_date = work_date_obj
            editing_entry.hours_worked = entry_data['hours_worked']
            editing_entry.drive_time = entry_data['drive_time']
            editing_entry.mileage = entry_data['mileage']
            editing_entry.comments = entry_data['comments']
            editing_entry.save()
            return redirect(f"/timesheet/?date={work_date_obj.isoformat()}")

        valid_entries = []
        form_rows = []
        submission_errors = []

        for index in get_entry_indices(request.POST) or ['1']:
            values = get_submitted_form_values(request.POST, index)
            entry_data, errors, is_active = validate_time_entry_values(values)
            if not is_active:
                continue
            form_rows.append(build_form_row(index, values, errors=errors))
            if errors:
                submission_errors.extend([f"Entry {index}: {error}" for error in errors])
                continue
            valid_entries.append(entry_data)

        if submission_errors:
            if not form_rows:
                form_rows = [build_form_row('1', get_empty_form_values())]
            entries, total_hours, total_miles = get_timesheet_entries(employee, work_date_obj)
            context = build_timesheet_context(
                jobs=jobs,
                workcodes=workcodes,
                non_job_codes=non_job_codes,
                selected_date=work_date_obj.isoformat(),
                hour_options=hour_options,
                drive_time_options=drive_time_options,
                entries=entries,
                total_hours=total_hours,
                total_miles=total_miles,
                form_rows=form_rows,
                submission_errors=submission_errors,
            )
            return render(request, 'core/timesheet.html', context)

        for entry_data in valid_entries:
            TimeEntry.objects.create(
                employee=employee,
                work_date=work_date_obj,
                **entry_data,
            )

        return redirect(f"/timesheet/?date={work_date_obj.isoformat()}")

    entries, total_hours, total_miles = get_timesheet_entries(employee, selected_date_obj)
    context = build_timesheet_context(
        jobs=jobs,
        workcodes=workcodes,
        non_job_codes=non_job_codes,
        selected_date=selected_date,
        hour_options=hour_options,
        drive_time_options=drive_time_options,
        entries=entries,
        total_hours=total_hours,
        total_miles=total_miles,
        editing_entry=editing_entry,
    )
    return render(request, 'core/timesheet.html', context)


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
    ).select_related('employee__user', 'job', 'work_code').order_by('id')

    return build_export_response(entries, f'timesheet-{work_date.isoformat()}.csv')


@login_required
@user_passes_test(is_authorized, login_url='/')
def export_jobs_list(request):
    export_type = request.GET.get('export_type')
    employee_id = request.GET.get('employee') or 'all'

    entries = TimeEntry.objects.select_related('employee__user', 'job', 'work_code').order_by(
        'work_date', 'employee__user__last_name', 'employee__user__first_name', 'id'
    )

    if export_type == 'range':
        start_date = parse_work_date(request.GET.get('start_date'))
        end_date = parse_work_date(request.GET.get('end_date'))
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        entries = entries.filter(work_date__range=(start_date, end_date))
        filename = f'jobs-list-{start_date.isoformat()}-to-{end_date.isoformat()}.csv'
    else:
        selected_date = parse_work_date(request.GET.get('date'))
        entries = entries.filter(work_date=selected_date)
        filename = f'jobs-list-{selected_date.isoformat()}.csv'

    if employee_id != 'all':
        entries = entries.filter(employee_id=employee_id)

    return build_export_response(entries, filename)
