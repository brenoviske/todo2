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

Copy `.env.example` to `.env`, then set separate, private random values for `SECRET_KEY` and `JWT_SECRET_KEY`, plus your `OPENAI_API_KEY`. For local HTTP development, leave `COOKIE_SECURE=false`; set it to `true` when serving the app over HTTPS in production. Start the app:

```bash
python app.py
```

Visit http://127.0.0.1:5000 and create an account. SQLite database `tasks.db` is created automatically in Flask's instance folder. To use PostgreSQL in production, install a PostgreSQL driver such as `psycopg[binary]` and set `DATABASE_URL` to a SQLAlchemy connection URL.

## Dependencies

The packages installed by `requirements.txt` are Flask (web server and routes), Flask-SQLAlchemy (relational ORM), Flask-JWT-Extended (JWT access tokens in HttpOnly cookies, with CSRF protection), OpenAI (server-side Responses API client), and python-dotenv (loads `.env`). SQLite is included with Python, so a separate database package is not needed for local use.

For deployment, set `FLASK_DEBUG=false`, set strong independent random `SECRET_KEY` and `JWT_SECRET_KEY` values, set `COOKIE_SECURE=true`, and configure a persistent production database. The browser never receives the JWT in JavaScript; it is stored in an HttpOnly cookie. Unsafe form and API requests must pass the JWT double-submit CSRF check. Never commit `.env` or expose the OpenAI key in frontend code.

## Backend layout

- `app.py` initializes Flask and SQLAlchemy, defines the HTTP routes, and delegates account and task operations to their controllers.
- `extensions.py` holds the shared SQLAlchemy database extension.
- `users/` contains the user model, DAO (database operations), and account controller (validation and account rules).
- `tasks/` contains the task model, DAO, and task controller.

The task composer includes a name, deadline, priority (low, medium, or high), and optional notes. Tasks can be edited from the list. On startup, the app adds the priority column to an existing SQLite task table without removing existing records.

The **Estatísticas** page is available at `/metrics`. Its metrics are calculated in `tasks/controller.py` from the signed-in user's tasks and include completion totals, overdue tasks, upcoming deadlines, and a seven-day task creation chart.

The Daymark SVG app icon is served from `static/daymark-icon.svg` and registered as the browser favicon and web app manifest icon.
