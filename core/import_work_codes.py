from pathlib import Path

from core.reference_data import import_reference_data_path


def run():
    file_path = Path(__file__).resolve().parent.parent / 'AllWorkCodes.csv'
    result = import_reference_data_path('work_codes', file_path)

    print('\n=== WORK CODE IMPORT COMPLETE ===')
    print(f"Work Codes Created: {result['created']}")
    print(f"Work Codes Updated: {result['updated']}")
    print(f"Work Codes Deactivated: {result['deactivated']}")
    print(f"Skipped Rows: {result['skipped']}")
    print('=================================\n')
