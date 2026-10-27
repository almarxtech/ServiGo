# ServiGo — Home Services (customer bookings + smarter AI estimates)

**Deploying via GitHub → PythonAnywhere?** See [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) for PowerShell and PythonAnywhere setup steps, WSGI configuration, static files, and secret handling.

Django home-services marketplace. This update corrects **who can change bookings**, adds an **estimate that still works without an AI key**, and preserves existing customer booking history when service listings are removed.

## Booking ownership (website and REST API)

| Operation | Customer | Provider |
| --- | --- | --- |
| Create booking | Yes | No |
| Edit booking date and problem description | **Own** Pending / Accepted | **No** |
| Delete booking | **Own** Pending / Accepted / Cancelled | **No** |
| Accept booking | No | **Own service's Pending** bookings |
| Reject booking (mark Cancelled) | No | **Own service's Pending / Accepted** bookings |
| Mark completed | No | **Own service's Accepted** bookings |
| Edit/delete service | No | **Own** services only |

After a customer edits an already **Accepted** booking, its status changes to **Pending** so the provider can approve the new details. Completed booking records are kept as history.

**Important:** Removing a service *archives* its listing, rather than deleting related bookings or reviews. Providers must first resolve any Pending/Accepted bookings. Archived services cannot be booked and do not show up in the service catalogue. Historical customer bookings remain visible. The dashboard's provider booking section now contains status actions, **not Edit/Delete buttons**.

## Smart cost estimate

Customers open **Book now**, choose a date, and describe the work in the **same form**. They can click **Get cost estimate** without saving a booking or losing their input.

- **Always available:** an indicative **₹ cost band** anchored to that provider's actual listed starting price, with a conservative rule-based complexity factor (Standard ×1.30, Moderate ×1.60, Complex ×2.00). This is a *rough illustration, not a market price, quote, or ML prediction*. The provider must confirm the final price after assessing the job.
- **If an AI provider is configured:** Gemini or Hugging Face generates *specific advice* about preparation, inspection and price-driving factors. AI-generated text does not change the numeric band, to avoid invented price figures.
- **If AI is missing/fails:** customers still receive the cost band and meaningful practical guidance. The UI indicates whether guidance came from AI or the built-in guide, rather than pretending it is AI.
- The **chat assistant** uses a real AI provider when configured, otherwise displays standard support guidance and a visible non-AI indicator. Session chat context is capped to the most recent three exchanges.

### AI setup

Create a `.env` file in the `home_services` directory by copying `.env.example`.

1. To enable Gemini, get a valid API key from [Google AI Studio](https://aistudio.google.com/apikey) and set `GEMINI_API_KEY=your_key_here`. Default model is `gemini-3.5-flash-lite`, which you can change using `GEMINI_MODEL=`. Your key/project must have access to the selected model.
2. Alternatively set `HF_API_KEY=your_HF_token` with permission for **Inference Providers**. By default this uses `HF_MODEL=openai/gpt-oss-120b:fastest`; change it to any chat-capable accessible model if needed. Provider usage may require credit/quota.
3. If both keys are set, Gemini is tried first and Hugging Face is the fallback.
4. Test after configuring the key:

```bash
python manage.py check_ai
```

For a config check **without making any paid API request**, run `python manage.py check_ai --skip-call`.

If it fails, check: active API key, model access, internet connection, billing/quota, model identifier and server logs. We cannot test live vendor responses without your valid key and connectivity. Do **not** place an API key in HTML, JavaScript, screenshots or a public Git repository.

## Install / run (Windows PowerShell)

```powershell
cd home_services
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

macOS/Linux: use `python3 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`, then run the same `pip`, `migrate` and `runserver` commands.

Visit http://127.0.0.1:8000/

**Existing project upgrade:** this ZIP intentionally excludes `db.sqlite3` to avoid overwriting your real bookings. It adds migration **`marketplace/0003_booking_problem_description.py`**. You MUST run `python manage.py migrate` before launching the updated app, and **back up your own latest `db.sqlite3` first**. Keep *your* database from the existing project and copy the updated code/migration onto it. If you start with a fresh folder, `python manage.py migrate` creates a new empty database.

The ZIP does not include `.env` (keys), an installed virtual environment or `__pycache__`. If you already have an `.env`, merge its keys and settings into your newly created `.env`. `TIME_ZONE` is configurable; `.env.example` uses `Asia/Kolkata`—change it if your customers are in a different region. The UI retains `₹` currency from the original project.

## Run checks

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test marketplace
```

Tests verify customer edit/delete, provider-only status changes, API role boundaries, protected history, archive behavior, model-mocked AI calls, input validation and keyless estimates.

## Security and deployment notes

Status-changing endpoints require POST and CSRF; API methods enforce the same permission rules. Service deletion is soft-archive for booking history integrity. The original allauth social-provider integrations are left installed; configure their credentials separately. Before deploying, set a secure secret, `DEBUG=False`, correct `ALLOWED_HOSTS`, HTTPS, email provider, static asset hosting and backups.


## AI diagnostics (when chat shows a standard guide)

In your project directory, put your actual key in `.env` (do not include quotes
or share the key publicly):

```env
GEMINI_API_KEY=your_real_google_ai_studio_key
GEMINI_MODEL=gemini-3.5-flash-lite
HF_API_KEY=
```

The model ID `gemini-3.5-flash-lite` is supported by Google. You can leave
Hugging Face unset while debugging Gemini. Run:

```powershell
python manage.py check_ai --skip-call
python manage.py check_ai
python manage.py runserver
```

`--skip-call` verifies whether the server detects your key; the second command
actually calls the model. Never paste your API key into chat or screenshots.

- HTTP 401: check the API key.
- HTTP 403: API permission, region or billing access restriction.
- HTTP 404: model ID is not available to the project/account.
- HTTP 429: quota/rate limit or billing limit.
- Network/timeout: internet connection, proxy or firewall.

If the model call fails, the app uses its non-AI guide and *explicitly labels*
it as a fallback rather than pretending to be AI. AI-dependent advice requires
a working paid/free-tier provider account with whatever access Google/HF allow.

**For an existing project:** before replacing code, back up your folder, leave its `.env` and `db.sqlite3` untouched, replace code files, then run `python manage.py migrate` and restart the server.


## Optional visual polish / animations (this update)

This package now includes `marketplace/static/marketplace/motion.css` and
`marketplace/static/marketplace/motion.js`, loaded globally through `base.html`.
They add a subtle hero float, card and button hover effects, on-scroll reveal,
animate-once dashboard number counters, chat typing indicator, a thin reading
progress line, a back-to-top button, and smooth chat opening. Animations are
front-end-only: **no changes to customer/provider booking permissions, AI keys,
models, database schema, or Django views**.

The visual effects **respect `prefers-reduced-motion`** (Windows: Accessibility
→ Visual effects; other operating systems offer similar settings). The
reveal feature is an enhancement only: when JavaScript is disabled or the
browser lacks `IntersectionObserver`, content remains visible. The assistant
still requires a working AI API key to provide AI-generated responses; these
animations do not modify AI access or reliability.

**When upgrading an existing project**, add `motion.css`, `motion.js`, and the
updated `base.html` together. Keep your own `.env` and `db.sqlite3` and do
not replace or publish them. If the page appears unchanged, restart the
server and hard refresh with `Ctrl+F5` to clear older static CSS/JS.


## New visual dashboard update: service categories + booking progress

The next polished ServiGo version adds:

- **Real category shortcuts on the customer dashboard.** Click a category to filter the actual active service listings (or click **All services** to clear filters). The category dropdown and text search still work.
- **Colorful, lightweight category illustrations** for service cards and service detail pages, plus matching booking icons. Standard categories such as Plumbing, Electrical, Cleaning, Painting, Carpentry, AC/HVAC, Appliances, Gardening, Pest Control, Security and Moving have dedicated icon/color themes. Unknown provider-defined category names use a neutral, safe fallback.
- **A status-aware booking progress timeline**, driven by the saved status on each booking: `Requested → Accepted → Completed`. Cancelled bookings show a separate closed-request message instead of pretending the work progressed.
- Customer and provider controls remain distinct: **customers** edit/delete eligible bookings; **providers** accept/reject/complete requests and edit/archive only their own services. An edited accepted booking returns to Pending, and the timeline updates automatically when the page is next loaded.
- Responsive layout and reduced-motion safeguards. These visuals require **no schema migration and no external stock images**. Font Awesome and Bootstrap use the site's existing CDN links.

New code files: `marketplace/templatetags/service_visuals.py` (fixed-safe icon mappings) and `marketplace/static/marketplace/visuals.css` (category designs and timeline). `dashboard.html`, `service_detail.html`, `book_service.html`, `base.html`, and tests are updated.

### Update your existing project

1. Back up your existing Django project.
2. Extract this ZIP and copy its code into your project folder, **keeping your own `.env` and `db.sqlite3`** (neither is included here).
3. In your existing virtual environment run:

```powershell
python manage.py migrate
python manage.py check
python manage.py test marketplace
python manage.py runserver
```

4. Hard refresh your web browser using `Ctrl + F5` so `visuals.css` loads. On a deployed server also collect static files and configure static hosting as usual.

**61 automated tests passed** for this version, including seven new category/timeline/accessibility checks. This upgrade changes visual presentation; it does not change provider/customer permissions or any AI credentials/integration.


## New: custom admin dashboard, complaints & advance requests

See **[NEW_FEATURES_AND_DEPLOY.md](NEW_FEATURES_AND_DEPLOY.md)** for roles, screenshots to test, a safety explanation of manual payments, and GitHub/PythonAnywhere update instructions.

- Staff / superusers: `/staff/dashboard/` — platform counts, reply to customer/provider complaints, verify/reject manually reported advance payments.
- Customers & providers: `/complaints/` — submit a private support issue and see admin replies.
- Customers: a **Request advance** option on Accepted bookings; admin verification is manual. **No actual payment is processed by this code.**
- `ADVANCE_PAYMENT_INSTRUCTIONS` is optional and belongs in the private production `.env` file.
- Run `python manage.py migrate` after upgrading to create the two new tables.
- `requests` is now listed in `requirements.txt` to support Google allauth during deployment.
