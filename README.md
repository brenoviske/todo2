# Daymark — Flask todo app

A personal task planner built with Flask, SQLAlchemy, SQLite, and an optional OpenAI planning assistant. Each account sees and manages only its own tasks, and users can update their profile, change their password, or delete their account from Account settings.

## Requirements

- Python 3.10 or newer
- pip
- An OpenAI API key to use the chat assistant (the rest of the app works without one)

## Install and run

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set separate, private random values for `SECRET_KEY` and `JWT_SECRET_KEY` in your existing `.env`, plus your `OPENAI_API_KEY`. For local HTTP development, leave `COOKIE_SECURE=false`; set it to `true` when serving the app over HTTPS in production. Start the app:

```bash
python app.py
```

Visit http://127.0.0.1:5000 and create an account. SQLite database `tasks.db` is created automatically when `DATABASE_URL` is not changed. For MySQL, use a SQLAlchemy URL in the form `mysql+pymysql://user:password@host:3306/database`; the `PyMySQL` driver is included in `requirements.txt`. Railway's `.internal` database hostname is only reachable from services running inside Railway. For local development, use SQLite, a Railway tunnel, or the database's public TCP URL.

## Deploying on Railway

Deploy the Flask app and MySQL database as separate services in the same Railway project and environment. The `Procfile` starts the Flask app with Gunicorn and binds it to Railway's assigned `$PORT`. Gunicorn is installed on Linux deployments and skipped on Windows development environments.

In the Flask service's Railway Variables, set `DATABASE_URL` to a reference to the MySQL service's `MYSQL_URL`, for example `${{MySQL.MYSQL_URL}}` when that database service is named `MySQL`. Use the exact Railway service name in the reference. The internal `*.railway.internal` database address will then resolve from the deployed Flask service. Do not use that private address from your Windows machine.

Set the Flask service's `APP_BASE_URL` to its public HTTPS URL, `COOKIE_SECURE=true`, and `FLASK_DEBUG=false`. Add `SECRET_KEY`, `JWT_SECRET_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PLUS`, and any optional `OPENAI_API_KEY` as Railway service variables. Keep local credentials in `.env`; do not commit that file. Configure Stripe's production webhook to use `https://your-app-domain/stripe/webhook` and its production signing secret.

## Dependencies

The packages installed by `requirements.txt` are Flask (web server and routes), Flask-SQLAlchemy (relational ORM), Flask-JWT-Extended (JWT access tokens in HttpOnly cookies, with CSRF protection), PyMySQL (MySQL driver), Stripe's Python SDK (hosted Checkout and billing portal), OpenAI (server-side Responses API client), and python-dotenv (loads `.env`). Gunicorn is installed on Linux for Railway production serving and is skipped on Windows. SQLite is included with Python, so a separate database package is not needed for local use.

For deployment, set `FLASK_DEBUG=false`, set strong independent random `SECRET_KEY` and `JWT_SECRET_KEY` values, set `COOKIE_SECURE=true`, and configure a persistent production database. The browser never receives the JWT in JavaScript; it is stored in an HttpOnly cookie. Unsafe form and API requests must pass the JWT double-submit CSRF check. Never commit `.env` or expose API keys in frontend code.

## Backend layout

- `app.py` initializes Flask and SQLAlchemy, defines the HTTP routes, and delegates account and task operations to their controllers.
- `extensions.py` holds the shared SQLAlchemy database extension.
- `users/` contains the user model, DAO (database operations), and account controller (validation and account rules).
- `tasks/` contains the task model, DAO, and task controller.

The task composer includes a name, deadline, priority (low, medium, or high), and optional notes. Tasks can be edited from the list. On startup, the app adds the priority column to an existing SQLite task table without removing existing records.

The **Estatísticas** page is available at `/metrics`. Its metrics are calculated in `tasks/controller.py` from the signed-in user's tasks and include completion totals, overdue tasks, upcoming deadlines, and a seven-day task creation chart.

The Daymark SVG app icon is served from `static/daymark-icon.svg` and registered as the browser favicon and web app manifest icon.

## Subscription billing

Signed-in users get a seven-day Daymark Plus trial. After it expires, task, planning, metrics, and assistant features are blocked; users can still access plan, billing, profile, and logout pages. Daymark Plus is priced at R$ 200 per month. New registrations begin their trial immediately; existing accounts without a subscription get a trial the first time they sign in after this feature is deployed.

Anyone can open `/plans` before creating an account. Choosing Plus starts the sign-up flow and then opens `/billing/checkout/plus`; signed-in users can also use `/billing` to view their account plan. The checkout page becomes active after its Stripe configuration is complete. Expired users remain blocked until Stripe confirms a subscription.

Stripe billing is implemented with hosted Checkout, the customer billing portal, and a signature-verified webhook. Add these values to your existing `.env` (never in browser code):

| Variable | Value |
| --- | --- |
| `STRIPE_SECRET_KEY` | Secret API key from Stripe. Use a test key while setting up. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for the webhook endpoint configured below. |
| `STRIPE_PRICE_PLUS` | Stripe recurring Price ID for Daymark Plus. |
| `APP_BASE_URL` | Public base URL of this app, such as `https://your-domain.example`; use `http://127.0.0.1:5000` locally. |

In Stripe, create a Daymark Plus product and a recurring monthly price of BRL 200, then copy its Price ID to `STRIPE_PRICE_PLUS`. Configure a webhook endpoint at `https://your-domain.example/stripe/webhook` (for local development, forward Stripe CLI events to `http://127.0.0.1:5000/stripe/webhook`). Subscribe it to `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, and `invoice.payment_failed`. Copy the endpoint's signing secret (`whsec_...`) into `STRIPE_WEBHOOK_SECRET` and restart/redeploy the app.

The checkout button becomes available once all three Stripe values are present. A user who subscribes during the app trial is charged when that same seven-day trial ends; subscribing after it ends starts billing immediately. Checkout and portal sessions are created server-side; webhook events are signature-verified and their event IDs recorded to make retries idempotent. The success redirect only displays confirmation and never grants access on its own. Account deletion expires an open Checkout Session and cancels an existing Stripe subscription before removing local billing data; deletion stops if Stripe cannot confirm those actions. Use Stripe test mode and test cards before switching to live keys. Enable/configure Stripe's customer portal before customers try to manage billing.

## Project study: structure and high impact improvements

_Preserved from an earlier repository review; observed-state notes may have changed since that review._

## Executive summary

Daymark is a small, server-rendered task planner built with Flask, SQLAlchemy, SQLite (or a configured SQLAlchemy database), Jinja templates, and a small amount of browser JavaScript. The project already has useful product foundations: user-owned task queries, hashed passwords, cookie-based JWT authentication with CSRF checks, and a clear visual identity.

The largest opportunity is to move from a promising local application toward a dependable product that is safer to deploy, easier to change, and more useful as task lists grow. The best first investments are configuration and secret hygiene, a real migration path, automated coverage of account and task ownership rules, and a more focused task workflow (search, filters, sorting, and pagination).

This is an analysis and proposal only. No application files were changed as part of the study.

## Current structure

| Area | Files | Responsibility |
|---|---|---|
| Application and HTTP | `app.py`, `extensions.py` | Flask setup, authentication hooks, routes, chat endpoint, database initialization |
| User domain | `users/model.py`, `users/dao.py`, `users/controller.py` | User persistence, password hashing, account rules |
| Task domain | `tasks/model.py`, `tasks/dao.py`, `tasks/controller.py` | Task persistence, validation, dashboard and metrics calculations |
| Server-rendered UI | `templates/*.html` | Authentication, dashboard, metrics, profile, and task editing views |
| Browser behavior and styling | `static/app.js`, `static/style.css`, icon and manifest | Theme, dates, chat requests, visual design |
| Setup and dependencies | `README.md`, `requirements.txt` | Local setup and deployment notes |

The project uses a straightforward layered design: routes call controllers, controllers call DAOs, and models represent database records. This is a good scale-appropriate starting point. The main boundary issue is that `app.py` still owns a lot of unrelated concerns, including app configuration, session behavior, task/account routes, external AI calls, and schema migration logic.

## What is already working well

- Task reads and edits are scoped to the signed-in user's ID in the DAO.
- Passwords are stored as Werkzeug password hashes, not plaintext.
- Authentication uses HttpOnly JWT cookies and enables CSRF protection for unsafe requests.
- Task and account rules are separated from route handlers in controller modules.
- Templates escape rendered user text by default, and chat output is inserted in the browser as text.
- The UI includes useful basics: task priorities, optional notes, due dates, completion, editing, account management, and progress summaries.
- The project is small enough to improve incrementally without a full rewrite.

## High impact findings and proposals

### 1. Make deployment configuration safe and consistent

**Observed:** The README tells developers to copy `.env.example`, but the file is absent from the repository. The workspace also has an untracked `.env`; `.gitignore` does not ignore `.env`.

**Why it matters:** This makes setup instructions fail as written and increases the chance that local credentials or API keys are accidentally added to version control. The current fallback also uses `SECRET_KEY` as the JWT secret when `JWT_SECRET_KEY` is missing, while the README asks for separate values.

**Proposal:** Add a sanitized `.env.example`, add `.env` (and common environment variants) to `.gitignore`, and validate required production settings at startup. Require independent secrets and secure cookies when running in production. Keep local defaults convenient only in explicit development mode.

**Priority:** P0 — first, before deployment or sharing the repository.

### 2. Replace startup schema edits with versioned migrations

**Observed:** `create_app()` calls `db.create_all()` and then directly alters the task table to add `priority` if missing.

**Why it matters:** This handles one historical schema change, but it will become brittle as fields and indexes evolve. Startup may unexpectedly attempt database writes, and schema behavior becomes difficult to inspect or roll back consistently across SQLite and MySQL.

**Proposal:** Introduce Flask-Migrate/Alembic, check migrations into source control, and make deployment run an explicit upgrade step. Keep a documented migration path for existing SQLite databases.

**Priority:** P0 for persistent or shared deployments; P1 for local-only use.

### 3. Add automated checks for the critical account and task guarantees

**Observed:** No test files or test runner configuration are present in the tracked project structure.

**Why it matters:** User isolation, login/session behavior, validation, and account deletion are core promises of the app. These are easy to regress while adding features and hard to validate manually on every change.

**Proposal:** Establish pytest with an isolated temporary SQLite database and app factory fixtures. Cover registration/login/logout, password changes, CSRF on unsafe routes, user A being unable to view or mutate user B's tasks, task validation, and account deletion. Add concise route/controller coverage before broader UI tests.

**Priority:** P0 — create a safety net before significant feature work.

### 4. Make task lists useful beyond a small number of records

**Observed:** The dashboard fetches every task and calculates counts in Python; the metrics page loads all tasks and computes daily counts with repeated scans. There is no search, filter, sort control, or pagination in the task list.

**Why it matters:** Response time and rendered page size grow with the user's entire history. Users also have limited ways to find the next relevant task once their list gets large.

**Proposal:** Add query parameters for status, priority, due-date window, and text search; make sort order explicit; paginate results. Move summary counts and date aggregations into SQL queries. Add indexes based on actual filters (for example, user/status/due date) after confirming query patterns.

**Priority:** P1 — strongest product and scalability improvement after baseline reliability.

### 5. Make dates and time zones explicit

**Observed:** Creation timestamps use naive `datetime.utcnow`, metrics use the server's `date.today()`, and browser displays use the viewer's local timezone. This can disagree around midnight or when the server and user are in different zones.

**Why it matters:** A task may appear overdue or be counted on the wrong day for users in a different timezone, especially around date boundaries.

**Proposal:** Decide whether deadlines are calendar dates in the user's timezone or absolute instants. Store timestamps as timezone-aware UTC, store a user timezone if personalized day boundaries are needed, and calculate dashboard/metrics dates against that timezone. Add boundary-focused tests.

**Priority:** P1 — important before supporting users across time zones.

### 6. Treat the AI assistant as a metered external feature

**Observed:** `/api/chat` creates a new OpenAI client for each request, has no visible message-size or rate limit, sends up to 40 task titles and notes to the provider, and catches every exception under one generic response.

**Why it matters:** Large requests can increase cost and latency; repeated requests can be abused; notes may include sensitive information. Broad exception handling hides useful distinctions between configuration, provider, and transient failures.

**Proposal:** Cap message and context sizes, set request timeouts, add per-user throttling, and make the task-context sharing behavior clear to users. Reuse a configured client where appropriate. Log provider error categories without logging task content or API secrets, and expose consistent user-safe errors. Consider an opt-in setting to disable AI context sharing.

**Priority:** P1 if the assistant is enabled for real users; P2 if it remains a local experiment.

### 7. Split application wiring from feature routes

**Observed:** `app.py` is 301 lines and combines configuration, auth lifecycle, routes for three domains, chat integration, and migration behavior.

**Why it matters:** Every feature change touches a central file, and route-level behavior is harder to reason about in isolation.

**Proposal:** Keep `create_app()` focused on configuration and extension setup. Move task, account, and chat routes into Flask blueprints. Move AI provider access behind a small service module. Keep the existing controller/DAO split unless domain complexity justifies further layers.

**Priority:** P2 — do alongside related feature work, after test coverage exists.

### 8. Improve task workflow and accessibility

**Observed:** The dashboard provides create, complete, edit, and delete actions, but no list search/filtering. Edit and delete controls are visually hidden until hover on larger screens. Delete confirmation exists only for deleting an account, not an individual task.

**Proposal:** Add fast status/priority filters, clear overdue/today grouping, keyboard-visible actions on focus, confirmation or undo for task deletion, and a more accessible task state announcement after updates. Consider bulk completion/archive once the basic list controls are in place.

**Priority:** P1/P2 — validate with a few real task-management scenarios before committing to a larger redesign.

### 9. Make the UI assets easier to maintain

**Observed:** `static/style.css` is 52 very long lines, with many compact rules and appended feature sections. Most page layouts are duplicated between templates.

**Why it matters:** The browser can load this, but developers have a harder time finding component rules and safely changing responsive or theme behavior.

**Proposal:** Reformat CSS, group styles by shared components and page, and extract repeated navigation/sidebar markup into Jinja partials. Preserve the current visual design while reducing duplicate sources of truth.

**Priority:** P2 — maintainability improvement; pair with related UI changes.

## Suggested delivery sequence

### Phase 1: Secure and reproducible foundation

1. Fix `.env.example` and `.gitignore`; verify repository history and status before any commit involving configuration.
2. Add production configuration validation and explicit development/production behavior.
3. Add a test harness for auth, CSRF, task ownership, and account deletion.
4. Establish migrations and document how existing databases are upgraded.

### Phase 2: Better everyday task use

1. Add filters, search, sorting, and pagination.
2. Move dashboard counts and metrics to database-level aggregates.
3. Improve keyboard access, focus states, and task deletion recovery.
4. Clarify deadline and timezone semantics.

### Phase 3: Product growth and operational readiness

1. Add AI request limits, bounded context, privacy controls, and operational error handling.
2. Split routes into blueprints and isolate the AI service.
3. Add structured logging, health checks, and a deployment guide for the chosen host/database.
4. Consider larger product capabilities such as recurring tasks, reminders, labels/projects, and calendar integration based on user feedback.

## Measures of success

- A new developer can set up the app using only the checked-in README and example configuration.
- Production startup fails clearly when security-critical configuration is missing.
- Existing databases upgrade through repeatable, reviewed migrations.
- Tests prevent cross-account task access and protect session/CSRF behavior.
- Dashboard response size and query work remain bounded as task history grows.
- Users can find tasks by status, priority, text, and due date without scanning the whole list.
- AI request volume, context size, and error categories can be monitored without exposing private task content.

## Scope notes

This study is based on the repository files and project structure. The `.env` file was not opened or inspected. No runtime tests, dependency installs, database inspection, or deployment checks were performed. The README references `.env.example`, but that file was not present in the repository listing.
