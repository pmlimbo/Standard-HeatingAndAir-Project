import csv
from django.contrib.auth.models import User
from core.models import Employee


def run():
    created_users = 0
    updated_users = 0
    created_employees = 0
    skipped = 0

    print("\n=== STARTING EMPLOYEE IMPORT ===\n")

    with open('AllEmployeesFile.csv', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        print(f"Headers detected: {reader.fieldnames}\n")

        for i, row in enumerate(reader, start=1):
            try:
                emp_code = row.get('EmpCD')
                full_name = row.get('Employee_Name', '').strip()
                password = row.get('Password', '').strip()

                if not emp_code:
                    print(f"[Row {i}] Skipped (missing EmpCD)")
                    skipped += 1
                    continue

                emp_code = emp_code.strip().lower()

                # Split name
                name_parts = full_name.split()
                first_name = name_parts[0] if name_parts else ''
                last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ''

                user, created = User.objects.get_or_create(
                    username=emp_code,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                    }
                )

                if created:
                    print(f"[Row {i}]  CREATED USER → {emp_code}")
                    created_users += 1
                else:
                    print(f"[Row {i}]  UPDATED USER → {emp_code}")
                    updated_users += 1

                # Always update password + name
                user.set_password(password)
                user.first_name = first_name
                user.last_name = last_name
                user.save()

                emp_obj, emp_created = Employee.objects.get_or_create(user=user)

                if emp_created:
                    print(f"          Employee record created")

                print(f"         Name: {first_name} {last_name}")
                print(f"         Password set\n")

            except Exception as e:
                print(f"[Row {i}]  ERROR: {e}")
                skipped += 1

    print("\n=== IMPORT COMPLETE ===")
    print(f"Users Created: {created_users}")
    print(f"Users Updated: {updated_users}")
    print(f"Employees Created: {created_employees}")
    print(f"Skipped Rows: {skipped}")
    print("========================\n")