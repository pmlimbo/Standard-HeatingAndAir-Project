import csv
import io
from pathlib import Path

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

from .models import Employee, Job, ReferenceDataUpload, WorkCode

REFERENCE_DATASETS = (
    {
        'key': 'jobs',
        'label': 'Jobs',
        'download_label': 'Download Current Jobs',
        'upload_label': 'Upload Jobs CSV',
        'filename': 'current-jobs.csv',
    },
    {
        'key': 'employees',
        'label': 'Employees',
        'download_label': 'Download Current Employees',
        'upload_label': 'Upload Employees CSV',
        'filename': 'current-employees.csv',
    },
    {
        'key': 'work_codes',
        'label': 'Work Codes',
        'download_label': 'Download Current Work Codes',
        'upload_label': 'Upload Work Codes CSV',
        'filename': 'current-work-codes.csv',
    },
    {
        'key': 'non_job_codes',
        'label': 'Non Job Codes',
        'download_label': 'Download Current Non Job Codes',
        'upload_label': 'Upload Non Job Codes CSV',
        'filename': 'current-non-job-codes.csv',
    },
)

REFERENCE_DATASET_MAP = {dataset['key']: dataset for dataset in REFERENCE_DATASETS}


def get_reference_dataset(dataset_key):
    dataset = REFERENCE_DATASET_MAP.get(dataset_key)
    if not dataset:
        raise ValueError(f'Unknown reference dataset: {dataset_key}')
    return dataset


def normalize_header(value):
    return (value or '').strip().lstrip('\ufeff').lower()


def load_csv_rows(file_obj):
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)

    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError('The uploaded CSV must include a header row.')

    headers = {normalize_header(field_name) for field_name in reader.fieldnames}
    rows = []
    for raw_row in reader:
        rows.append({
            normalize_header(key): (value or '').strip()
            for key, value in raw_row.items()
        })

    return headers, rows


def split_full_name(full_name):
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ''
    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    return first_name, last_name


def format_employee_name(user):
    full_name = f'{user.first_name} {user.last_name}'.strip()
    return full_name or user.username


@transaction.atomic
def import_employees(file_obj):
    headers, rows = load_csv_rows(file_obj)
    if 'empcd' not in headers:
        raise ValueError('Employees CSV must include an EmpCD column.')

    created_users = 0
    updated_users = 0
    created_employees = 0
    skipped = 0

    for row in rows:
        employee_code = (row.get('empcd') or row.get('employee_code') or '').strip()
        if not employee_code:
            skipped += 1
            continue

        employee_code = employee_code.lower()
        full_name = (row.get('employee_name') or '').strip()
        first_name = (row.get('first_name') or '').strip()
        last_name = (row.get('last_name') or '').strip()
        password = (row.get('password') or '').strip()
        has_name_data = bool(full_name or first_name or last_name)

        if full_name and not (first_name or last_name):
            first_name, last_name = split_full_name(full_name)

        user, created = User.objects.get_or_create(username=employee_code)
        if created:
            created_users += 1
        else:
            updated_users += 1

        if created or has_name_data:
            user.first_name = first_name
            user.last_name = last_name

        if password:
            user.set_password(password)
        elif created:
            user.set_unusable_password()

        user.save()

        _, employee_created = Employee.objects.get_or_create(user=user)
        if employee_created:
            created_employees += 1

    return {
        'created_users': created_users,
        'updated_users': updated_users,
        'created_employees': created_employees,
        'skipped': skipped,
    }


@transaction.atomic
def import_jobs(file_obj):
    headers, rows = load_csv_rows(file_obj)
    if 'jobnumber' not in headers and 'job_number' not in headers:
        raise ValueError('Jobs CSV must include a JobNumber column.')

    created = 0
    updated = 0
    skipped = 0
    has_job_name = 'job_name' in headers
    has_job_address = 'job_address' in headers or 'street_address' in headers
    has_status_code = 'status_code' in headers

    for row in rows:
        job_number = (row.get('jobnumber') or row.get('job_number') or '').strip()
        if not job_number:
            skipped += 1
            continue

        job = Job.objects.filter(job_number=job_number).order_by('id').first()
        if job is None:
            job = Job(job_number=job_number)
            created += 1
        else:
            updated += 1

        if has_job_name:
            job.job_name = row.get('job_name', '')
        if has_job_address:
            job.street_address = row.get('job_address') or row.get('street_address', '')
        if has_status_code:
            job.status_code = (row.get('status_code') or '').strip().upper()

        job.save()

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
    }


@transaction.atomic
def import_work_codes(file_obj, *, requires_job):
    headers, rows = load_csv_rows(file_obj)
    if 'code' not in headers:
        raise ValueError('Work code CSV must include a Code column.')

    created = 0
    updated = 0
    skipped = 0
    seen_codes = set()
    has_description = 'task' in headers or 'description' in headers

    for row in rows:
        code = (row.get('code') or '').strip()
        if not code:
            skipped += 1
            continue

        description = row.get('task') or row.get('description', '')
        work_code = WorkCode.objects.filter(
            code=code,
            requires_job=requires_job,
        ).order_by('id').first()

        if work_code is None:
            work_code = WorkCode(code=code, requires_job=requires_job)
            created += 1
        else:
            updated += 1

        if has_description:
            work_code.description = description
        work_code.is_active = True
        work_code.save()
        seen_codes.add(code)

    if seen_codes:
        deactivated = WorkCode.objects.filter(
            requires_job=requires_job,
            is_active=True,
        ).exclude(code__in=seen_codes).update(is_active=False)
    else:
        deactivated = 0

    return {
        'created': created,
        'updated': updated,
        'deactivated': deactivated,
        'skipped': skipped,
    }


def import_reference_data(dataset_key, file_obj):
    if dataset_key == 'jobs':
        return import_jobs(file_obj)
    if dataset_key == 'employees':
        return import_employees(file_obj)
    if dataset_key == 'work_codes':
        return import_work_codes(file_obj, requires_job=True)
    if dataset_key == 'non_job_codes':
        return import_work_codes(file_obj, requires_job=False)
    raise ValueError(f'Unknown reference dataset: {dataset_key}')


def format_upload_timestamp(value):
    if not value:
        return ''
    return date_filter(timezone.localtime(value), 'M j, Y g:i A T')


def record_reference_data_upload(dataset_key, filename=''):
    upload, _ = ReferenceDataUpload.objects.update_or_create(
        dataset=dataset_key,
        defaults={
            'last_uploaded_at': timezone.now(),
            'last_uploaded_filename': filename,
        },
    )
    return upload


def import_reference_data_path(dataset_key, file_path):
    path = Path(file_path)
    with path.open('rb') as file_obj:
        result = import_reference_data(dataset_key, file_obj)
    record_reference_data_upload(dataset_key, path.name)
    return result


def build_reference_data_items():
    upload_map = {
        upload.dataset: upload
        for upload in ReferenceDataUpload.objects.all()
    }
    items = []
    for dataset in REFERENCE_DATASETS:
        status = upload_map.get(dataset['key'])
        items.append({
            **dataset,
            'last_uploaded_at': status.last_uploaded_at if status else None,
            'last_uploaded_display': format_upload_timestamp(status.last_uploaded_at) if status else '',
            'last_uploaded_filename': status.last_uploaded_filename if status else '',
        })
    return items


def build_reference_data_export_response(dataset_key):
    dataset = get_reference_dataset(dataset_key)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{dataset["filename"]}"'
    writer = csv.writer(response)

    if dataset_key == 'jobs':
        writer.writerow(['JobNumber', 'Job_Address', 'Job_Name', 'Status_Code'])
        for job in Job.objects.order_by('job_number', 'id'):
            writer.writerow([
                job.job_number,
                job.street_address,
                job.job_name,
                job.status_code,
            ])
        return response

    if dataset_key == 'employees':
        writer.writerow(['EmpCD', 'Employee_Name', 'Password'])
        for employee in Employee.objects.select_related('user').order_by('user__username'):
            writer.writerow([
                employee.user.username,
                format_employee_name(employee.user),
                '',
            ])
        return response

    writer.writerow(['Code', 'TASK'])
    for work_code in WorkCode.objects.filter(
        requires_job=(dataset_key == 'work_codes'),
        is_active=True,
    ).order_by('code', 'id'):
        writer.writerow([
            work_code.code,
            work_code.description,
        ])

    return response


def summarize_reference_data_import(dataset_key, result):
    label = get_reference_dataset(dataset_key)['label']

    if dataset_key == 'employees':
        parts = [
            f"{result['created_users']} users created",
            f"{result['updated_users']} users updated",
            f"{result['created_employees']} employee records created",
        ]
    else:
        parts = [
            f"{result['created']} created",
            f"{result['updated']} updated",
        ]
        if 'deactivated' in result:
            parts.append(f"{result['deactivated']} deactivated")

    parts.append(f"{result['skipped']} skipped")
    return f"{label} upload complete: {', '.join(parts)}."
