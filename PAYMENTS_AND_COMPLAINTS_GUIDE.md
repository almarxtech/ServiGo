# ServiGo — Complaints + Online Advance Payments (academic project)

This version builds on the existing custom admin. **Customer/Provider complaints show both parties** when linked to a booking. The customer can choose either **Manual Transfer** or **Razorpay Standard Checkout** for an accepted booking. Payment records are managed inside the **ServiGo Admin Workspace**, not Django Admin.

## 1. Complaints

- URL: `/complaints/`; customer or provider opens it and chooses a booking, category, subject and description.
- For categories **Booking, Service and Payment**, linking a booking is required: the Admin Complaint Desk `/staff/complaints/` displays Customer, Provider, Service, Booking ID, and who complained.
- For **Account/Other** complaints a general complaint without a booking is still allowed; without a booking there is no verified counterpart to show.
- Customer can only attach their own bookings; provider can only attach bookings of their own services. Only staff can view all complaints; other customers/providers cannot read them.
- Admin can reply and mark complaints Open / In Review / Resolved / Dismissed.

## 2. Payment methods

On an **Accepted** booking, the customer can open `/booking/<id>/advance/` and see:

**A. Manual request:** Choose UPI / Bank Transfer / Other Transfer, enter advance amount, and optionally a transfer reference. Admin verifies independently at `/staff/payments/` before marking `Verified`. This form **does not send or collect funds**. Add trustworthy business bank/UPI instructions only in server `.env` (`ADVANCE_PAYMENT_INSTRUCTIONS`).

**B. Razorpay online checkout:** Requires Razorpay keys. Customer specifies an amount **not above the listed service price**. Django creates a Razorpay order on the server; Standard Checkout lets Razorpay display eligible UPI Intent / QR, card, netbanking and wallet methods. Availability of methods depends on merchant activation and settings. ServiGo NEVER asks for card details, CVV, UPI PIN, OTP, or stores them.

Checkout state: `Awaiting Payment` (NOT paid) → `Gateway Paid` only after the server verifies the checkout HMAC and fetches a **captured** payment from Razorpay **for the exact order/amount/currency**. A Razorpay `payment.captured` signed webhook also marks payment captured if checkout redirect was interrupted. Repeated webhook delivery is safe. Server records Razorpay payment ID, actual method (`upi`, `card`, `netbanking`, etc.), and `test`/`live` mode. **Admin cannot manually mark a pending Razorpay checkout as paid.**

### IMPORTANT: Is it free?

- **Razorpay TEST MODE is free for academic demonstration.** Test UPI/card payments are simulations, **no actual funds move**.
- **Real gateway payments are NOT necessarily free.** Razorpay standard pricing advertises no setup/annual maintenance charges, but successful transactions can incur platform/transaction charges and tax. Live activation requires merchant account eligibility, KYC and an approved Indian business/bank account. Check current official terms before accepting real funds.
- Do not use real payment data to test your college app. Production/live mode needs operational readiness, merchant approval, refund/reconciliation policies, and manual end-to-end review.
- For 2026 UPI changes, **use Standard Checkout's UPI Intent / Dynamic QR**, not legacy manual UPI ID collect requests (deprecated from 28 Feb 2026).

### 3. Razorpay Test Mode key setup

1. Open [Razorpay Dashboard](https://dashboard.razorpay.com/). Create an account (merchant eligibility may vary).
2. Switch to **Test Mode**. Generate Test Key ID (`rzp_test_...`) and Test Key Secret.
3. Keep both private in your **server** `.env` (do NOT commit to GitHub):

```dotenv
RAZORPAY_KEY_ID=rzp_test_YOUR_ID
RAZORPAY_KEY_SECRET=YOUR_PRIVATE_SECRET
RAZORPAY_WEBHOOK_SECRET=YOUR_OWN_RANDOM_WEBHOOK_SECRET
```

4. In Razorpay Dashboard, set payment capture to **Auto Capture** for orders. Configure webhook endpoint using HTTPS:

```text
https://YOUR_USERNAME.pythonanywhere.com/payments/razorpay/webhook/
```

Subscribe to `payment.captured`. Use **the same webhook secret** in Dashboard and `.env`; this is independent from the Razorpay API Key Secret. If running locally, Razorpay cannot reach `127.0.0.1` directly; test checkout callback locally, configure the webhook after deployment or via a trusted HTTPS test tunnel.
5. Restart Django server locally / **Reload** the PythonAnywhere web app to read `.env` changes. Test **one small simulated payment**, then inspect `/staff/payments/` for `Gateway Paid (TEST)` and `gateway_method=upi/card/...`.
6. If the page reports `Awaiting Payment`, the payment was **not confirmed as captured**. Check Razorpay Dashboard and server logs, do not mark it manually Verified.

**After your merchant account is approved for live mode**, replace test credentials with live credentials only after planning reconciliation/refunds; be careful of outstanding test checkout orders before switching modes. Never expose the Key Secret in JavaScript, templates or screenshots. Only the public Key ID is sent to Standard Checkout.

**Refunds are NOT automatic** in this project. A customer/provider cancellation with a payment retains the booking as cancelled and retains the payment record; any genuine refunds must be handled separately under the merchant's policies. This is an academic/demo integration, NOT a production-audited financial platform.

## 4. Upgrade current local project

1. Back up the current entire project, especially `.env` and `db.sqlite3`.
2. Extract this ZIP, copy **source files only** to your existing Git working copy. This ZIP intentionally excludes `.env` and databases; preserve yours.
3. In Windows PowerShell from directory containing `manage.py`:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test marketplace
python manage.py runserver
```

4. New DB migration: `marketplace/0005_advancepayment_gateway_method_and_more.py`. Old customer bookings, complaints, and manual payment records are preserved. Existing admin routes remain unchanged.
5. Visit `/staff/dashboard/`, `/staff/complaints/`, `/staff/payments/` (staff only); visit `/complaints/` or an accepted booking as customer/provider.

## 5. GitHub → PythonAnywhere

Push updated **source** to your GitHub repo from the local machine; ensure `git status` excludes `.env`, `.sqlite3`, `.venv`, `venv` and API keys.

```powershell
git status
git add .
git status
git commit -m "Display complaint parties and add Razorpay test checkout"
git push origin main
```

On PythonAnywhere, **save any uncommitted changes first**, especially the earlier registration backend fix:

```bash
cd ~/ServiGo
git status
git pull --ff-only origin main
source ~/ServiGo-venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py collectstatic --noinput
```

Configure private Razorpay Test Mode variables in `~/ServiGo/.env`, and PythonAnywhere **Web → Reload**. Keep your current `ALLOWED_HOSTS`, `DJANGO_SECRET_KEY`, `DEBUG=False`, `CSRF_TRUSTED_ORIGINS` and existing database intact. Then test with test mode, check the admin Payment records, and inspect Web → Error log if needed.

PythonAnywhere free account allowlist currently includes `api.razorpay.com`, but merchant/network availability and individual service access may still affect requests.

### Developer checks

Test with `python manage.py test marketplace`; this suite mocks external Razorpay requests and does NOT prove your individual merchant/API credentials work live. Server-side captured status, signature verification, CSRF, ownership and admin authorization have automated tests. Real checkout must be separately tested with your own Test Mode account.
