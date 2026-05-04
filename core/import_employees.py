from pathlib import Path

from core.reference_data import import_reference_data_path


def run():
    file_path = Path(__file__).resolve().parent.parent / 'ALLEmployeesFile.csv'
    result = import_reference_data_path('employees', file_path)

    print('\n=== EMPLOYEE IMPORT COMPLETE ===')
    print(f"Users Created: {result['created_users']}")
    print(f"Users Updated: {result['updated_users']}")
    print(f"Employees Created: {result['created_employees']}")
    print(f"Skipped Rows: {result['skipped']}")
    print('================================\n')
