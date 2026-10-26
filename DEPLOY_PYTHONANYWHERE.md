# ServiGo: GitHub + PythonAnywhere Deployment

This guide is for the Django project folder that contains `manage.py` and `requirements.txt`. PythonAnywhere's server is **Linux**, so use the **Bash console** there, not Windows PowerShell.

## 0. Before uploading code

- Make a local backup of your existing `.env` and `db.sqlite3`.
- This ZIP contains neither `.env` nor `db.sqlite3`.
- `.gitignore` blocks keys, databases, the virtual environment, and generated staticfiles from Git.
- Never paste your Gemini/Hugging Face key or Django secret into GitHub, commits, screenshots or chat.
- If you ever accidentally commit secrets, rotate the exposed credentials immediately; `.gitignore` does not erase existing commits.

## 1. GitHub: Windows PowerShell in `C:\Users\ADMIN\home_services`

Create an empty GitHub repository named, for example, `servigo` (do not initialize it with a README; the code has one). Open PowerShell **inside the directory containing `manage.py`**.

```powershell
cd C:\Users\ADMIN\home_services
git init
git branch -M main
git add .
git status
# Check that .env, db.sqlite3, and venv are NOT listed.
git commit -m "Prepare ServiGo for deployment"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/servigo.git
git push -u origin main
```

If an `origin` remote already exists, use `git remote -v` first and update it with `git remote set-url origin <url>` rather than adding a duplicate.

## 2. PythonAnywhere: create project and virtualenv

PythonAnywhere > **Consoles** > **Bash**:

```bash
cd ~
git clone https://github.com/YOUR_GITHUB_USERNAME/servigo.git
cd servigo
python3.13 -m venv ~/.virtualenvs/servigo-venv
source ~/.virtualenvs/servigo-venv/bin/activate
pip install -r requirements.txt
```

Choose **Python 3.13** for your PythonAnywhere web app if available; Django 6.1 requires Python >= 3.12. If Python 3.13 is not offered, choose Python 3.12 for both app and virtualenv, and substitute `python3.12` above. Your account's system image determines the available versions.

## 3. Create a private `.env` on PythonAnywhere

```bash
cd ~/servigo
cp .env.example .env
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
nano .env
```

Use the printed key in `.env` as `DJANGO_SECRET_KEY`. Configure:

```dotenv
DJANGO_SECRET_KEY=PASTE_A_NEW_PRIVATE_DJANGO_KEY_HERE
DEBUG=False
ALLOWED_HOSTS=YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com
TIME_ZONE=Asia/Kolkata
GEMINI_API_KEY=PASTE_YOUR_PRIVATE_GEMINI_KEY_HERE
# Optional backup model:
HF_API_KEY=
```

`TIME_ZONE` should match your service region. Never add the **real** `.env` to Git.

## 4. Prepare database and static files

In the same active virtualenv:

```bash
cd ~/servigo
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py check_ai --skip-call
python manage.py createsuperuser
```

`check --deploy` may warn about HSTS and `SECURE_SSL_REDIRECT`. Force HTTPS at the PythonAnywhere Web tab as directed above; only enable HSTS after confirming all pages and subdomains are HTTPS-ready. Review all deployment-check warnings. If the hosted site should use your **existing** customers/bookings, upload your private, backed-up SQLite DB directly to PythonAnywhere as `~/servigo/db.sqlite3` (never through GitHub) **before** running `migrate`. Back it up first and avoid overwriting any live data. New installs start with an empty database.

## 5. PythonAnywhere: Web tab

1. **Add a new web app** > **Manual configuration** (not the automated Django setup) > **Python 3.13** or the same Python version as your venv.
2. Set Virtualenv to `/home/YOUR_PYTHONANYWHERE_USERNAME/.virtualenvs/servigo-venv`.
3. Set source-code directory and working directory to `/home/YOUR_PYTHONANYWHERE_USERNAME/servigo`.
4. Open the **WSGI configuration file link on the Web tab**, not `core/wsgi.py`, and use:

```python
import os
import sys

path = '/home/YOUR_PYTHONANYWHERE_USERNAME/servigo'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

5. **Static files** mapping in Web tab:

| URL | Directory |
| --- | --- |
| `/static/` | `/home/YOUR_PYTHONANYWHERE_USERNAME/servigo/staticfiles` |

6. In **Web > Security**, enable **Force HTTPS** after confirming HTTPS works. PythonAnywhere supplies HTTPS for `*.pythonanywhere.com`. Do not separately enable Django `SECURE_SSL_REDIRECT` unless you have carefully verified reverse-proxy behavior; it can cause redirect loops.
7. Hit **Reload** on the Web tab. Visit `https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com/`.

Do NOT run `manage.py runserver` for the public web app. Use **Web > Error log** if it fails.

## 6. Smoke test

- Home, registration/login, customer/provider dashboards
- Customer creates/edits/cancels a booking; provider accepts/rejects/completes one
- Service icons and animated dashboard styles load; browser has no 404s for `/static/` files
- AI test in Bash: `python manage.py check_ai` (this makes a real external API call and may consume API quota)
- Check browser and PythonAnywhere error logs for errors

The remote AI endpoints (`generativelanguage.googleapis.com`, `router.huggingface.co`) currently appear on PythonAnywhere's free-account allowlist, but key/model/quota issues can still cause failed AI calls.

## 7. Future updates

On Windows:

```powershell
git add .
git commit -m "Update ServiGo"
git push
```

On PythonAnywhere Bash:

```bash
cd ~/servigo
git pull
source ~/.virtualenvs/servigo-venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Reload the web app using the PythonAnywhere Web tab after each code update. Database backups are your responsibility.

Official docs:
- https://help.pythonanywhere.com/pages/DeployExistingDjangoProject
- https://help.pythonanywhere.com/pages/DjangoStaticFiles
- https://help.pythonanywhere.com/pages/PythonVersions
- https://help.pythonanywhere.com/pages/ForcingHTTPS
