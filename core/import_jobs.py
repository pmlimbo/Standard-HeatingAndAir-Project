from pathlib import Path

from core.reference_data import import_reference_data_path


#from core.import_jobs import run
#run()

def run():
    file_path = Path(__file__).resolve().parent.parent / 'AllJobNumbers.csv'
    result = import_reference_data_path('jobs', file_path)

    print('\n=== JOB IMPORT COMPLETE ===')
    print(f"Jobs Created: {result['created']}")
    print(f"Jobs Updated: {result['updated']}")
    print(f"Skipped Rows: {result['skipped']}")
    print('===========================\n')
