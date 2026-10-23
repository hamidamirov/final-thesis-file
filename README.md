# Student Finance Management

A Django web application that helps university students track personal income, expenses, and monthly category budgets. Users can create an account, manage their own transactions, and review their financial totals from a dashboard.

## Requirements

- Python 3.10 or newer
- MySQL Server
- Git

## Local setup on Windows

Open this project folder in VS Code, then select **Terminal → New Terminal**.

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the Python dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

   Update `.env` with your own Django secret key and MySQL connection settings. Never commit `.env` or share its contents. The `.env.example` file contains placeholders only.

4. Create the database in MySQL. For example:

   ```sql
   CREATE DATABASE student_finance CHARACTER SET utf8mb4;
   ```

   Make sure `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in `.env` match your MySQL configuration.

5. Create the database tables and an administrator account:

   ```powershell
   python manage.py migrate
   python manage.py createsuperuser
   ```

6. Start the development server:

   ```powershell
   python manage.py runserver
   ```

   Open `http://127.0.0.1:8000/` in your browser. The database health endpoint is `http://127.0.0.1:8000/health/database/`.

## Main features

- User registration and login
- Income and expense tracking
- Transaction categories, dates, and notes
- Dashboard totals and recent transactions
- Monthly category budgets
- Django admin interface at `/admin/`

## GitHub safety

The `.gitignore` file excludes `.env` and virtual environment folders. Review `git status` before committing to make sure that credentials and other private files are not included.
