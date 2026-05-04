from pathlib import Path

from core.reference_data import import_reference_data_path


def run():
    file_path = Path(__file__).resolve().parent.parent / 'AllNonJobCodes.csv'
    result = import_reference_data_path('non_job_codes', file_path)

    print('\n=== NON JOB CODE IMPORT COMPLETE ===')
    print(f"Non Job Codes Created: {result['created']}")
    print(f"Non Job Codes Updated: {result['updated']}")
    print(f"Non Job Codes Deactivated: {result['deactivated']}")
    print(f"Skipped Rows: {result['skipped']}")
    print('====================================\n')
