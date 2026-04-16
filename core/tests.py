from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import Employee, Job, TimeEntry, WorkCode


class TimesheetViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='worker1',
            password='testpass123',
            first_name='Casey',
            last_name='Worker',
        )
        self.client.login(username='worker1', password='testpass123')
        self.job = Job.objects.create(job_number='JOB-100', job_name='Test Job', street_address='123 Main')
        self.job_code = WorkCode.objects.create(code='100', description='Install', requires_job=True, is_active=True)
        self.non_job_code = WorkCode.objects.create(code='SM', description='Safety Meeting', requires_job=False, is_active=True)

    def test_timesheet_get_creates_employee_record(self):
        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Employee.objects.filter(user=self.user).exists())

    def test_timesheet_post_saves_multiple_rows(self):
        response = self.client.post(
            reverse('timesheet'),
            data={
                'date': '2026-04-16',
                'job_1': 'JOB-100 | Test Job | 123 Main',
                'work_code_1': '100 - Install',
                'non_job_code_1': '',
                'hours_1': '2',
                'drive_time_1': '0.5',
                'mileage_1': '10',
                'comments_1': 'On site',
                'job_2': '',
                'work_code_2': '',
                'non_job_code_2': 'SM',
                'hours_2': '1',
                'drive_time_2': '0',
                'mileage_2': '0',
                'comments_2': 'Training',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeEntry.objects.count(), 2)
        self.assertEqual(TimeEntry.objects.filter(job__isnull=True, work_code=self.non_job_code).count(), 1)

    def test_invalid_date_falls_back_to_today(self):
        response = self.client.get(reverse('timesheet'), {'date': 'not-a-date'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('selected_date', response.context)

    def test_delete_requires_post(self):
        employee = Employee.objects.create(user=self.user)
        entry = TimeEntry.objects.create(
            employee=employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='1.00',
            drive_time='0.25',
            mileage='5.00',
            comments='Delete me',
        )

        response = self.client.get(reverse('delete_entry', args=[entry.id]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(TimeEntry.objects.filter(id=entry.id).exists())

    def test_delete_removes_owned_entry(self):
        employee = Employee.objects.create(user=self.user)
        entry = TimeEntry.objects.create(
            employee=employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='1.00',
            drive_time='0.25',
            mileage='5.00',
            comments='Delete me',
        )

        response = self.client.post(reverse('delete_entry', args=[entry.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(TimeEntry.objects.filter(id=entry.id).exists())


class ReportsAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='worker2', password='testpass123')
        self.authorized_group = Group.objects.create(name='Authorized')

    def test_reports_requires_authorized_user(self):
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 302)

    def test_reports_allows_authorized_group(self):
        self.user.groups.add(self.authorized_group)
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
