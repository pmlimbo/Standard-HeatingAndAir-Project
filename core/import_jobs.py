import csv
from core.models import Job

#from core.import_jobs import run
#run()

def run():
    with open('AllJobNumbers.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            Job.objects.update_or_create(
                job_number=row['JobNumber'],
                defaults={
                    'job_name': row.get('Job_Name', ''),
                    'street_address': row.get('Job_Address', ''),
                }
            )

    print("Import complete")