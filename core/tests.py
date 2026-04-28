import csv
import io

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

    def test_timesheet_post_allows_blank_mileage(self):
        response = self.client.post(
            reverse('timesheet'),
            data={
                'date': '2026-04-16',
                'job_1': 'JOB-100 | Test Job | 123 Main',
                'work_code_1': '100 - Install',
                'non_job_code_1': '',
                'hours_1': '2',
                'drive_time_1': '0.5',
                'mileage_1': '',
                'comments_1': 'Mileage optional',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeEntry.objects.count(), 1)
        self.assertEqual(str(TimeEntry.objects.get().mileage), '0.00')

    def test_invalid_date_falls_back_to_today(self):
        response = self.client.get(reverse('timesheet'), {'date': 'not-a-date'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('selected_date', response.context)

    def test_timesheet_hides_add_customer_link(self):
        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('add_customer'))
        self.assertNotContains(response, 'Admin Login')
        self.assertNotContains(response, 'Admin Page')

    def test_timesheet_page_source_does_not_embed_lookup_values(self):
        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'JOB-100 | Test Job | 123 Main')
        self.assertNotContains(response, '100 - Install')
        self.assertNotContains(response, 'SM - Safety Meeting')

    def test_edit_mode_prefills_saved_entry(self):
        employee = Employee.objects.create(user=self.user)
        entry = TimeEntry.objects.create(
            employee=employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='2.00',
            drive_time='0.50',
            mileage='10.00',
            comments='Needs update',
        )

        response = self.client.get(reverse('timesheet'), {'date': '2026-04-16', 'edit': entry.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['editing_entry'].id, entry.id)
        self.assertEqual(response.context['form_rows'][0]['values']['job'], 'JOB-100 | Test Job | 123 Main')
        self.assertEqual(response.context['form_rows'][0]['values']['work_code'], '100 - Install')
        self.assertContains(response, 'Update Entry')

    def test_edit_mode_updates_existing_entry(self):
        employee = Employee.objects.create(user=self.user)
        entry = TimeEntry.objects.create(
            employee=employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='2.00',
            drive_time='0.50',
            mileage='10.00',
            comments='Needs update',
        )

        response = self.client.post(
            reverse('timesheet'),
            data={
                'editing_entry_id': entry.id,
                'date': '2026-04-17',
                'job_1': 'JOB-100 | Test Job | 123 Main',
                'work_code_1': '100 - Install',
                'non_job_code_1': '',
                'hours_1': '3',
                'drive_time_1': '1',
                'mileage_1': '12',
                'comments_1': 'Updated entry',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeEntry.objects.count(), 1)

        entry.refresh_from_db()
        self.assertEqual(entry.work_date.isoformat(), '2026-04-17')
        self.assertEqual(str(entry.hours_worked), '3.00')
        self.assertEqual(str(entry.drive_time), '1.00')
        self.assertEqual(str(entry.mileage), '12.00')
        self.assertEqual(entry.comments, 'Updated entry')

    def test_saved_entries_show_job_details_and_code_descriptions(self):
        employee = Employee.objects.create(user=self.user)
        TimeEntry.objects.create(
            employee=employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='2.00',
            drive_time='0.50',
            mileage='10.00',
            comments='Job entry',
        )
        TimeEntry.objects.create(
            employee=employee,
            job=None,
            work_code=self.non_job_code,
            work_date='2026-04-16',
            hours_worked='1.00',
            drive_time='0.25',
            mileage='0.00',
            comments='Non job entry',
        )

        response = self.client.get(reverse('timesheet'), {'date': '2026-04-16'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'JOB-100')
        self.assertContains(response, 'Test Job')
        self.assertContains(response, '123 Main')
        self.assertContains(response, '100 - Install')
        self.assertContains(response, 'SM - Safety Meeting')

    def test_invalid_submission_shows_errors_and_keeps_values(self):
        response = self.client.post(
            reverse('timesheet'),
            data={
                'date': '2026-04-16',
                'job_1': '',
                'work_code_1': '100 - Install',
                'non_job_code_1': '',
                'hours_1': '2',
                'drive_time_1': '0.5',
                'mileage_1': '',
                'comments_1': 'Keep this',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertContains(response, 'Job Number is required when using a Work Code.')
        self.assertContains(response, '100 - Install')
        self.assertContains(response, 'Keep this')

    def test_timesheet_requires_hours_greater_than_zero(self):
        response = self.client.post(
            reverse('timesheet'),
            data={
                'date': '2026-04-16',
                'job_1': 'JOB-100 | Test Job | 123 Main',
                'work_code_1': '100 - Install',
                'non_job_code_1': '',
                'hours_1': '0',
                'drive_time_1': '0.5',
                'mileage_1': '',
                'comments_1': 'Hours missing',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertContains(response, 'Hours must be greater than 0.')
        self.assertContains(response, 'Hours missing')

    def test_timesheet_shows_or_between_code_fields(self):
        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Or')

    def test_job_lookup_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('search_jobs'), {'q': 'JOB'})

        self.assertEqual(response.status_code, 302)

    def test_job_lookup_returns_filtered_matches(self):
        response = self.client.get(reverse('search_jobs'), {'q': 'JOB-100'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [
            {'label': 'JOB-100 | Test Job | 123 Main'},
        ])

    def test_work_code_lookups_return_filtered_matches(self):
        job_code_response = self.client.get(reverse('search_work_codes'), {'q': '100'})
        non_job_code_response = self.client.get(reverse('search_non_job_codes'), {'q': 'SM'})

        self.assertEqual(job_code_response.status_code, 200)
        self.assertEqual(job_code_response.json()['results'], [
            {'label': '100 - Install'},
        ])
        self.assertEqual(non_job_code_response.status_code, 200)
        self.assertEqual(non_job_code_response.json()['results'], [
            {'label': 'SM - Safety Meeting'},
        ])

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
        self.report_user = User.objects.create_user(
            username='employee99',
            password='testpass123',
            first_name='Alicia',
            last_name='Example',
        )
        self.report_employee = Employee.objects.create(user=self.report_user)

    def test_timesheet_hides_reports_link_for_unauthorized_user(self):
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('reports'))

    def test_timesheet_shows_reports_link_for_authorized_group(self):
        self.user.groups.add(self.authorized_group)
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('reports'))

    def test_timesheet_shows_reports_link_for_staff_user(self):
        self.user.is_staff = True
        self.user.save()
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('timesheet'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('reports'))

    def test_reports_requires_authorized_user(self):
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 302)

    def test_reports_allows_authorized_group(self):
        self.user.groups.add(self.authorized_group)
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Single Day Export')
        self.assertNotContains(response, reverse('add_customer'))
        self.assertContains(response, 'Go to Main Website')
        self.assertContains(response, 'Admin Login')
        self.assertContains(response, reverse('admin:login'))

    def test_reports_page_source_does_not_embed_employee_list(self):
        self.user.groups.add(self.authorized_group)
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Alicia Example (employee99)')
        self.assertNotContains(response, 'employee99')

    def test_reports_shows_admin_page_button_for_staff_user(self):
        self.user.is_staff = True
        self.user.save()
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Page')
        self.assertContains(response, reverse('admin:index'))
        self.assertNotContains(response, 'Admin Login')

    def test_employee_lookup_requires_authorized_user(self):
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('search_employees'), {'q': 'Ali'})

        self.assertEqual(response.status_code, 302)

    def test_employee_lookup_returns_filtered_matches_for_authorized_user(self):
        self.user.groups.add(self.authorized_group)
        self.client.login(username='worker2', password='testpass123')

        response = self.client.get(reverse('search_employees'), {'q': 'Ali'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [
            {'label': 'Alicia Example (employee99)', 'value': str(self.report_employee.id)},
        ])


class ReportsExportTests(TestCase):
    def setUp(self):
        self.authorized_group = Group.objects.create(name='Authorized')
        self.manager = User.objects.create_user(
            username='manager1',
            password='testpass123',
            first_name='Morgan',
            last_name='Manager',
        )
        self.worker = User.objects.create_user(
            username='worker3',
            password='testpass123',
            first_name='Taylor',
            last_name='Worker',
        )
        self.manager.groups.add(self.authorized_group)
        self.client.login(username='manager1', password='testpass123')

        self.job = Job.objects.create(job_number='JOB-200', job_name='Second Job', street_address='456 Oak')
        self.job_code = WorkCode.objects.create(code='200', description='Service', requires_job=True, is_active=True)

        self.manager_employee = Employee.objects.create(user=self.manager)
        self.worker_employee = Employee.objects.create(user=self.worker)

        TimeEntry.objects.create(
            employee=self.manager_employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='2.00',
            drive_time='0.50',
            mileage='8.00',
            comments='Manager day one',
        )
        TimeEntry.objects.create(
            employee=self.worker_employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-16',
            hours_worked='4.00',
            drive_time='1.00',
            mileage='15.00',
            comments='Worker day one',
        )
        TimeEntry.objects.create(
            employee=self.manager_employee,
            job=self.job,
            work_code=self.job_code,
            work_date='2026-04-17',
            hours_worked='3.00',
            drive_time='0.25',
            mileage='6.00',
            comments='Manager day two',
        )

    def test_export_jobs_list_single_day_all_employees(self):
        response = self.client.get(
            reverse('export_jobs_list'),
            {
                'export_type': 'single',
                'date': '2026-04-16',
                'employee': 'all',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row[1] for row in rows[1:]}, {'manager1', 'worker3'})
        self.assertEqual({row[3] for row in rows[1:]}, {'16-Apr-26'})

    def test_export_jobs_list_date_range_for_one_employee(self):
        response = self.client.get(
            reverse('export_jobs_list'),
            {
                'export_type': 'range',
                'start_date': '2026-04-16',
                'end_date': '2026-04-17',
                'employee': str(self.manager_employee.id),
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row[1] for row in rows[1:]}, {'manager1'})
        self.assertEqual({row[3] for row in rows[1:]}, {'16-Apr-26', '17-Apr-26'})
