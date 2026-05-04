import csv
from urllib.parse import urlencode
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import CustomerForm
from .models import Employee, Job, TimeEntry, WorkCode
from .reference_data import (
    build_reference_data_export_response,
    build_reference_data_items,
    format_upload_timestamp,
    get_reference_dataset,
    import_reference_data,
    record_reference_data_upload,
    summarize_reference_data_import,
)

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

LOOKUP_RESULT_LIMIT = 20


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


def get_job_status_data(job):
    if not job or not job.status_label:
        return None

    return {
        'code': job.normalized_status_code,
        'label': job.status_label,
        'tone': job.status_tone,
    }


def format_job_lookup_result(job):
    result = {
        'label': format_job_label(job),
    }
    status = get_job_status_data(job)
    if status:
        result.update({
            'status_code': status['code'],
            'status_label': status['label'],
            'status_tone': status['tone'],
        })
    return result


def format_work_code_label(work_code):
    return f"{work_code.code} - {work_code.description}"


def format_employee_label(employee):
    full_name = f"{employee.user.first_name} {employee.user.last_name}".strip()
    if full_name:
        return f"{full_name} ({employee.user.username})"
    return employee.user.username


def extract_lookup_value(value, separator):
    return (value or '').partition(separator)[0].strip()


def get_job_from_lookup_value(value):
    if not value:
        return None

    job_number = extract_lookup_value(value, ' | ')
    if not job_number:
        return None

    return Job.objects.filter(job_number=job_number).order_by('id').first()


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
        job = get_job_from_lookup_value(values['job'])
        if not job:
            errors.append('Select a valid Job Number.')

    work_code = None
    if values['work_code']:
        work_code_value = extract_lookup_value(values['work_code'], ' - ')
        work_code = WorkCode.objects.filter(
            code=work_code_value,
            is_active=True,
            requires_job=True,
        ).first()
        if not work_code:
            errors.append('Select a valid Work Code.')
    elif values['non_job_code']:
        non_job_code_value = extract_lookup_value(values['non_job_code'], ' - ')
        work_code = WorkCode.objects.filter(
            code=non_job_code_value,
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
        'non_job_code': format_work_code_label(entry.work_code) if not entry.work_code.requires_job else '',
        'hours': format_decimal_for_input(entry.hours_worked),
        'drive_time': format_decimal_for_input(entry.drive_time),
        'mileage': format_decimal_for_input(entry.mileage),
        'comments': entry.comments,
    }


def build_form_row(index, values=None, errors=None, title=None):
    values = values or get_empty_form_values()
    job_status = get_job_status_data(get_job_from_lookup_value(values.get('job')))

    return {
        'index': str(index),
        'title': title or f'Entry {index}',
        'values': values,
        'job_status': job_status,
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


def get_admin_access_context(user):
    if not is_authorized(user):
        return {
            'show_admin_access': False,
            'admin_access_url': '',
            'admin_access_label': '',
        }

    admin_index_url = reverse('admin:index')
    if user.is_staff or user.is_superuser:
        return {
            'show_admin_access': True,
            'admin_access_url': admin_index_url,
            'admin_access_label': 'Admin Page',
        }

    return {
        'show_admin_access': True,
        'admin_access_url': f"{reverse('admin:login')}?{urlencode({'next': admin_index_url})}",
        'admin_access_label': 'Admin Login',
    }


def build_timesheet_context(
    *,
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


def get_lookup_query(request, min_length):
    query = (request.GET.get('q') or '').strip()
    if len(query) < min_length:
        return ''
    return query


def get_work_code_lookup_results(query, *, requires_job):
    workcodes = WorkCode.objects.filter(
        is_active=True,
        requires_job=requires_job,
    ).filter(
        Q(code__icontains=query) | Q(description__icontains=query)
    ).order_by('code')[:LOOKUP_RESULT_LIMIT]
    return [{'label': format_work_code_label(work_code)} for work_code in workcodes]


@never_cache
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


@never_cache
@login_required
def search_jobs(request):
    query = get_lookup_query(request, min_length=2)
    if not query:
        return JsonResponse({'results': []})

    jobs = Job.objects.filter(
        Q(job_number__icontains=query) |
        Q(job_name__icontains=query) |
        Q(street_address__icontains=query) |
        Q(city__icontains=query)
    ).order_by('job_number')[:LOOKUP_RESULT_LIMIT]

    return JsonResponse({
        'results': [format_job_lookup_result(job) for job in jobs],
    })


@never_cache
@login_required
def search_work_codes(request):
    query = get_lookup_query(request, min_length=1)
    if not query:
        return JsonResponse({'results': []})

    return JsonResponse({
        'results': get_work_code_lookup_results(query, requires_job=True),
    })


@never_cache
@login_required
def search_non_job_codes(request):
    query = get_lookup_query(request, min_length=1)
    if not query:
        return JsonResponse({'results': []})

    return JsonResponse({
        'results': get_work_code_lookup_results(query, requires_job=False),
    })


@never_cache
@login_required
@user_passes_test(is_authorized, login_url='/')
def search_employees(request):
    query = get_lookup_query(request, min_length=2)
    if not query:
        return JsonResponse({'results': []})

    employees = Employee.objects.select_related('user').filter(
        Q(user__username__icontains=query) |
        Q(user__first_name__icontains=query) |
        Q(user__last_name__icontains=query)
    ).order_by('user__last_name', 'user__first_name', 'user__username')[:LOOKUP_RESULT_LIMIT]

    return JsonResponse({
        'results': [
            {'label': format_employee_label(employee), 'value': str(employee.id)}
            for employee in employees
        ],
    })


def get_reference_dataset_or_404(dataset_key):
    try:
        return get_reference_dataset(dataset_key)
    except ValueError as exc:
        raise Http404(str(exc)) from exc


def is_ajax_request(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@never_cache
@login_required
@user_passes_test(is_authorized, login_url='/')
def reports(request):
    today = date.today().isoformat()
    return render(request, 'core/reports.html', {
        'today': today,
        'reference_data_items': build_reference_data_items(),
        **get_admin_access_context(request.user),
    })


@never_cache
@login_required
@user_passes_test(is_authorized, login_url='/')
def download_reference_data(request, dataset_key):
    get_reference_dataset_or_404(dataset_key)
    return build_reference_data_export_response(dataset_key)


@never_cache
@login_required
@user_passes_test(is_authorized, login_url='/')
@require_POST
def upload_reference_data(request, dataset_key):
    dataset = get_reference_dataset_or_404(dataset_key)
    uploaded_file = request.FILES.get('csv_file')
    ajax_request = is_ajax_request(request)

    if not uploaded_file:
        error_message = f"Choose a CSV file to upload for {dataset['label']}."
        if ajax_request:
            return JsonResponse({'ok': False, 'message': error_message}, status=400)
        messages.error(request, error_message)
        return redirect('reports')

    try:
        result = import_reference_data(dataset_key, uploaded_file)
        upload_status = record_reference_data_upload(dataset_key, getattr(uploaded_file, 'name', ''))
    except UnicodeDecodeError:
        error_message = f"{dataset['label']} upload failed: the file must be UTF-8 CSV text."
        if ajax_request:
            return JsonResponse({'ok': False, 'message': error_message}, status=400)
        messages.error(request, error_message)
        return redirect('reports')
    except ValueError as exc:
        error_message = f"{dataset['label']} upload failed: {exc}"
        if ajax_request:
            return JsonResponse({'ok': False, 'message': error_message}, status=400)
        messages.error(request, error_message)
        return redirect('reports')

    success_message = summarize_reference_data_import(dataset_key, result)
    if ajax_request:
        return JsonResponse({
            'ok': True,
            'message': success_message,
            'last_uploaded_display': format_upload_timestamp(upload_status.last_uploaded_at),
            'last_uploaded_filename': upload_status.last_uploaded_filename,
        })

    messages.success(request, success_message)
    return redirect('reports')


@never_cache
@login_required
def timesheet(request):
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
        selected_date=selected_date,
        hour_options=hour_options,
        drive_time_options=drive_time_options,
        entries=entries,
        total_hours=total_hours,
        total_miles=total_miles,
        editing_entry=editing_entry,
    )
    return render(request, 'core/timesheet.html', context)


@never_cache
@login_required
@require_POST
def delete_entry(request, entry_id):
    entry = get_object_or_404(TimeEntry, id=entry_id)

    if entry.employee.user != request.user:
        return redirect('timesheet')

    date_str = entry.work_date.strftime("%Y-%m-%d")
    entry.delete()
    return redirect(f'/timesheet/?date={date_str}')


@never_cache
@login_required
def export_timesheet(request):
    work_date = parse_work_date(request.GET.get('date'))
    employee, _ = Employee.objects.get_or_create(user=request.user)

    entries = TimeEntry.objects.filter(
        employee=employee,
        work_date=work_date
    ).select_related('employee__user', 'job', 'work_code').order_by('id')

    return build_export_response(entries, f'timesheet-{work_date.isoformat()}.csv')


@never_cache
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
