# Tələbə maliyyəsinin idarə edilməsi

Universitet tələbələri üçün şəxsi maliyyəni qeyd etməyə kömək edən bakalavr işi layihəsi. Hazırkı mərhələ Django əsaslı ilkin skeletdir; hesablar və maliyyə funksiyaları hələ əlavə edilməyib.

## Tələblər

- Python 3.10 və ya daha yeni versiya
- MySQL Server
- VS Code və onun inteqrasiya olunmuş terminalı

## Windows-da yerli qurulum

VS Code-da layihə qovluğunu açın və **Terminal → New Terminal** seçin.

1. Python-un quraşdırıldığını yoxlayın:

   ```powershell
   python --version
   ```

2. Layihə üçün ayrıca virtual mühit yaradın və aktivləşdirin. Bu, kitabxanaları kompüterdəki digər Python layihələrindən ayırır:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Lazım olan Python kitabxanalarını quraşdırın:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   MySQL sürücüsü Django sənədlərinin tövsiyə etdiyi `mysqlclient`-dir. Windows-da quraşdırma xətası çıxarsa, xəta mətnini paylaşın; uyğun həlli seçək.

4. Nümunə mühit faylının surətini yaradın:

   ```powershell
   Copy-Item .env.example .env
   ```

   Sonra `.env` faylını VS Code-da açıb öz kompüterinizdə istifadə etdiyiniz MySQL verilənlər bazası, istifadəçi və parol dəyərlərini yazın. `DJANGO_SECRET_KEY` üçün də uzun, təsadüfi dəyər təyin edin. `.env` faylını GitHub-a yükləməyin.

5. MySQL-də `student_finance` adlı verilənlər bazası yaradın. Məsələn, MySQL terminalında:

   ```sql
   CREATE DATABASE student_finance CHARACTER SET utf8mb4;
   ```

   `.env` daxilindəki `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` və `DB_PORT` dəyərləri sizin MySQL sazlamalarınıza uyğun olmalıdır.

6. Tətbiqi başladın:

   ```powershell
   python manage.py runserver
   ```

   Brauzerdə `http://127.0.0.1:8000/` ünvanını açın. Verilənlər bazası bağlantısını `http://127.0.0.1:8000/health/database/` ünvanında yoxlayın. Uğurlu cavab `{"status":"ok"}` olacaq; bağlantı qurulmayıbsa, endpoint `503` qaytaracaq.

## Qeydlər

- Django admin ünvanı `/admin/`-dir. Admin istifadəçisi hələ yaradılmayıb.
- Məlumat bazası sxemi və tətbiq funksiyaları ayrıca razılaşdırılıb növbəti mərhələlərdə əlavə ediləcək.
- `.env.example` yalnız nümunə açar adları və saxta doldurucu dəyərlər saxlayır.
