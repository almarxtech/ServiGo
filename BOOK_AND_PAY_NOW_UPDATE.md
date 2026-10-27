# ServiGo — Book & Pay Now (Razorpay)

## What changed

A customer can pay **while making a booking**: the booking form now has
**Book & Pay Now**, **Book & Pay Later**, and **Get cost estimate**.

1. Choose a service and appointment date.
2. **Book & Pay Now** records a **Pending** booking and creates ONE Razorpay order for the
   provider's **listed starting price**, treated as an advance. It redirects to the existing
   Razorpay Checkout page; click **Open Razorpay checkout** to select UPI/card/netbanking.
   This extra explicit click works reliably on browsers blocking redirected pop-ups.
3. Razorpay sends a payment id, order id and signature. ServiGo verifies the signature
   **AND** independently fetches the captured payment with the correct order, amount,
   and INR currency before recording **Gateway Paid**. A signed webhook can also confirm it.
4. Provider may then Accept/Reject the Pending booking. Payment never auto-accepts a booking.
   A rejection or cancellation does **not** automatically refund money; contact admin.
5. **Book & Pay Later** saves a Pending booking without calling the gateway. The customer
   can click **Pay now** in My Bookings before *or* after provider approval.
6. Staff can track these advances at `/staff/payments/`. Test Mode amounts are tracked
   separately from live receipts.

## Safety

- No card data / UPI PIN / OTP is stored by ServiGo. Checkout is hosted by Razorpay.
- Requires the customer's own login and proper role; other customers cannot access it.
- CSRF-protected forms and server-verified payment capture.
- New unique UUID booking submission key prevents browser retries and double-clicks from
  creating duplicate bookings/orders. Existing bookings have a nullable field and survive.
- If a Razorpay order request fails, the entire initial Book & Pay Now operation rolls
  back; no booking/payment is saved. Choose Pay Later or retry.
- A captured payment stays in the audit history even if the booking is later cancelled.
- No automatic refunds, payouts, settlements, or escrow. Test keys do not collect money.
- In production a live merchant must meet provider KYC/payment-method requirements.

## Configure

Never put keys in GitHub. Inside local/server `.env`:

```env
RAZORPAY_KEY_ID=rzp_test_YOUR_PUBLIC_KEY
RAZORPAY_KEY_SECRET=YOUR_PRIVATE_TEST_SECRET
RAZORPAY_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET
```

Webhook (optional, strongly recommended for real reliability):
`https://your-site/payments/razorpay/webhook/` (enable payment.captured).

## Local update from this ZIP

1. Back up `.env` and `db.sqlite3` from the **current working project**.
2. Copy updated code into the project folder. **Never overwrite** those two files.
3. Activate the existing virtual environment, then run:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Database migration **0006_booking_submission_key** must apply successfully.

## GitHub → PythonAnywhere

First push the updated code to `https://github.com/almarxtech/ServiGo` from your
local cloned repository. **Do not** commit `.env` or `db.sqlite3`; run `git status` to
verify. On PythonAnywhere (username `ServiGo`), back up server database and `.env`.
If `git status` shows local changes, save/compare them before pulling; an earlier
registration-login fix must not be silently discarded. Then:

```bash
cd ~/ServiGo
source ~/ServiGo-venv/bin/activate
git status
git pull --ff-only origin main
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
python manage.py test
```

After commands succeed, go to **PythonAnywhere → Web → Reload**.
The web app will not update by only uploading a ZIP to this conversation.

## Demo checklist

- Customer books with **Pay Later** → Pending → dashboard Pay now works.
- Customer books with **Pay Now** → Razorpay test checkout → admin sees transaction.
- Retry the same booking token → still just one booking and one order.
- Provider can Accept after advance is captured.
- Provider rejects paid booking → admin refund attention, audit record preserved.
- Webhook and browser callback both verify signature/captured order/amount.

**Note:** Tests are provided in `marketplace/test_book_and_pay.py`; execute them in
your installed Django environment.
