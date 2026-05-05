# Windows Hosting

This project is configured for production-style hosting on Windows with:

- PostgreSQL
- Waitress bound to `127.0.0.1:8000`
- WhiteNoise serving collected static files
- Cloudflare Tunnel forwarding `standardactimesheet.com` to `http://127.0.0.1:8000`

## 1. Open PowerShell in the project folder

```powershell
cd C:\Users\piercel\PycharmProjects\DjangoProject\mysite
```

## 2. Create and activate the virtual environment

If `.venv` already exists, skip the first command.

```powershell
py -3.14 -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. .\.venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 4. Create the local environment file

If `.env` does not already exist:

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum required values in `.env`:

```env
DJANGO_SECRET_KEY=replace_with_a_long_random_secret_key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=standardactimesheet.com,www.standardactimesheet.com,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://standardactimesheet.com,https://www.standardactimesheet.com
DJANGO_STATIC_ROOT=staticfiles
DJANGO_USE_X_FORWARDED_HOST=True

DB_NAME=timesheet_db
DB_USER=timesheet_user
DB_PASSWORD=replace_me
DB_HOST=your_postgres_host
DB_PORT=5432
DB_SSLMODE=disable
```

## 5. Run migrations

```powershell
python manage.py migrate
```

## 6. Collect static files

Run this any time static assets change.

```powershell
python manage.py collectstatic --noinput
```

Collected static files will be written to:

```text
.\staticfiles\
```

## 7. Start the site with Waitress

This project includes `serve_waitress.py`, which starts Waitress on `127.0.0.1:8000` by default and trusts proxy headers from the local Cloudflare Tunnel process.

```powershell
python serve_waitress.py
```

Expected bind target:

```text
http://127.0.0.1:8000
```

Optional Waitress overrides:

```powershell
$env:WAITRESS_HOST="127.0.0.1"
$env:WAITRESS_PORT="8000"
$env:WAITRESS_THREADS="8"
python serve_waitress.py
```

## 8. Cloudflare Tunnel target

Point Cloudflare Tunnel at:

```text
http://127.0.0.1:8000
```

## 9. Normal deployment update flow

Whenever you deploy code changes:

```powershell
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python serve_waitress.py
```
