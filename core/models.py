# core/models.py
from django.contrib.auth.models import User
from django.db import models

JOB_STATUS_LABELS = {
    'A': 'Active',
    'C': 'Complete',
    'F': 'Finished',
    'H': 'Hold',
    'I': 'Inactive',
    'P': 'Proposed',
}

JOB_STATUS_TONES = {
    'A': 'success',
    'C': 'success',
    'F': 'success',
    'H': 'warning',
    'I': 'danger',
    'P': 'warning',
}

HIDDEN_JOB_STATUSES = {'Z'}





class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# core/models.py
class JobType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class WorkCode(models.Model):
    code = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True)
    requires_job = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.description}"


class Job(models.Model):
    job_number = models.CharField(max_length=50)
    job_name = models.CharField(max_length=255, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    status_code = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.job_number

    @property
    def normalized_status_code(self):
        return (self.status_code or '').strip().upper()

    @property
    def status_label(self):
        code = self.normalized_status_code
        if not code:
            return ''
        if code in HIDDEN_JOB_STATUSES:
            return ''
        return JOB_STATUS_LABELS.get(code, code)

    @property
    def status_tone(self):
        code = self.normalized_status_code
        return JOB_STATUS_TONES.get(code, 'warning')


class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.username


class ReferenceDataUpload(models.Model):
    DATASET_CHOICES = [
        ('jobs', 'Jobs'),
        ('employees', 'Employees'),
        ('work_codes', 'Work Codes'),
        ('non_job_codes', 'Non Job Codes'),
    ]

    dataset = models.CharField(max_length=32, choices=DATASET_CHOICES, unique=True)
    last_uploaded_at = models.DateTimeField(null=True, blank=True)
    last_uploaded_filename = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.get_dataset_display()


class TimeEntry(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True)
    work_code = models.ForeignKey(WorkCode, on_delete=models.CASCADE)

    work_date = models.DateField()

    hours_worked = models.DecimalField(max_digits=4, decimal_places=2)
    drive_time = models.DecimalField(max_digits=4, decimal_places=2)
    mileage = models.DecimalField(max_digits=6, decimal_places=2)

    comments = models.TextField(blank=True)

    def __str__(self):
        return f"{self.employee} - {self.work_date}"
