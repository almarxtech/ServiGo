# ServiGo — Admin Dashboard, Complaints & Advance Requests

This release extends the **existing ServiGo Django/SQLite project**. It preserves existing accounts, bookings and services with a new additive migration (`marketplace.0004_complaints_advance_payments`).

## New pages

| URL | Who can use it | Purpose |
| --- | --- | --- |
| `/staff/dashboard/` | `is_staff=True` users / Django superusers only | Admin metrics, complaints, manual advances, recent bookings |
| `/complaints/` | Logged-in customer or provider | Submit complaints and read admin replies |
| `/booking/<id>/advance/` | The booking's customer, when accepted | Submit/update a manual advance request |
| `/admin/` | Authorized Django admin users | Standard database management |

## Complaints

Customers and providers can select their own associated booking (optional), a category, a subject, and a description. The form never accepts a booking belonging to another account or another provider. Regular users can view **only complaints they submitted**. Staff can respond and change status to `Open`, `In Review`, `Resolved`, or `Dismissed` from the **ServiGo admin workspace**. Resolving requires a response.

## Advance payments — IMPORTANT

**This app does not process money, debit cards, wallets, UPI, or bank accounts.** It records a *manual advance request* for staff verification; submitting a form is **NOT** proof that payment reached anyone. No card number, PIN, password, OTP, or bank-login credentials should ever be entered.

1. A customer places a service booking.
2. The provider accepts it.
3. The customer clicks **Request advance** on the accepted booking, chooses an amount <= the currently listed service price and a transfer method; a transfer reference is optional until the customer actually pays.
4. The new request appears on `/staff/dashboard/` as **Submitted**.
5. After confirming a real payment using the official payment channel, staff may mark it **Verified**, but only if a transfer reference is present. Otherwise staff can **Reject** with a reason.
6. The customer sees the advance status on their dashboard. They can correct/re-submit a rejected request; they cannot edit a verified one.

To display your own payment instructions (for example, a verified business UPI/account) set this **in the server's private `.env`**:

```dotenv
ADVANCE_PAYMENT_INSTRUCTIONS=Contact ServiGo admin for official transfer details. After transferring, return and enter the bank reference.
```

Do **not** place real financial account credentials, personal login credentials or API keys in code, README or GitHub. Without configured instructions, customers see a warning not to send money until they have admin-approved payment details. Never mark an advance Verified without independently seeing the funds in an account you control. For **actual online checkout**, payment gateway integration (Razorpay/Stripe etc.), secure webhooks, refund workflows and additional testing must be developed separately.

**Refund note:** If a booking has an advance record and a customer attempts to delete it, the booking is **cancelled instead of deleted**, retaining the payment record. No automatic refund happens; admin must handle this manually, including after provider rejection/cancellation.

## Safe update steps

### Local Windows (VS Code)

1. Make a backup of your existing project, `.env`, and `db.sqlite3`.
2. Extract the ZIP; copy updated project code on top of your local Git checkout while **keeping your old `.env` and `db.sqlite3`**. The ZIP does not include these local files.
3. Run:

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test marketplace
python manage.py runserver
```

4. Commit and push **only the source code**, not secrets or database:

```powershell
git status
git add .
git status
git commit -m "Add staff dashboard complaints and advance review"
git push origin main
```

`.gitignore` already excludes `.env`, virtual environments, `db.sqlite3`, `staticfiles/`. **Inspect `git status` before committing.**

### PythonAnywhere after pushing to GitHub

In a PythonAnywhere **Bash console** for the existing app:

```bash
cd ~/ServiGo
git status   # first resolve any local uncommitted changes; do not delete them
# only if the working tree is clean:
git pull --ff-only origin main
source ~/ServiGo-venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py collectstatic --noinput
```

- Preserve your existing `.env` and `db.sqlite3`; never replace the live database with a ZIP or a fresh DB.
- Configure `DEBUG=False`, real `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, CSRF origins on the server as before.
- In PythonAnywhere **Web > Reload**, click Reload after the update.
- Login as a **Django superuser/staff user**, then open `/staff/dashboard/`.
- Create a superuser only if required using `python manage.py createsuperuser`.
- Verify a test complaint and a test advance **without real money**.
- If the staff screen reports 500, check **Web > Error log**, especially migration `0004`.

### Local checks performed for this release

- Django 6.1.1 startup/system check.
- Database migration recognized; no outstanding model changes.
- Existing and new automated Django tests (see below).
- Python source compiled and ZIP excluded databases, secrets, and the local test virtual environment.

## Technical implementation

- New tables: `Complaint`, `AdvancePayment` (linked to `Booking`, with `PROTECT` for the advance trail).
- Role/ownership checks, CSRF-protected POST actions, no user-supplied ownership/status fields in public forms.
- Staff-only status transitions and independently confirmed verification.
- Customer-initiated accepted-booking changes still return to `Pending` for provider approval.
- Django `admin/` remains available. The two new record types are read-only in Django admin to encourage review via `/staff/dashboard/`.
- Existing registration backend fix included: specify `django.contrib.auth.backends.ModelBackend` for auto-login.
- Missing `requests` dependency from earlier PythonAnywhere deploy fixed in `requirements.txt`.
