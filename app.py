import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from sqlalchemy import inspect, text

from dotenv import dotenv_values, load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)
from openai import OpenAI

from extensions import db
from tasks import dao as task_dao
from tasks import planning as planning_service
from tasks import controller as task_controller
from tasks.model import Task  # Register task models before mapper initialization.
from tasks.rituals import DailyPlan, WeeklyReview  # Register planning models before mapper initialization.
from users import controller as user_controller
from users import dao as user_dao
from users.billing import PLANS, Subscription, get_or_create_subscription, subscription_state
from users.model import User  # Register the model with SQLAlchemy before create_all().
from users import stripe_service

ENV_FILE = Path(__file__).resolve().with_name(".env")
load_dotenv(ENV_FILE)

# A blank process-level setting should not mask a populated local .env value.
_file_env = dotenv_values(ENV_FILE)
for _name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_PLUS", "APP_BASE_URL"):
    if not (os.getenv(_name) or "").strip() and (_file_env.get(_name) or "").strip():
        os.environ[_name] = _file_env[_name].strip()

jwt = JWTManager()


def create_app():
    """Create the app and connect its HTTP routes to the domain controllers."""
    application = Flask(__name__)
    application.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    database_url = (os.getenv("DATABASE_URL") or "sqlite:///tasks.db").strip()
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    elif database_url.startswith("mysql://"):
        database_url = "mysql+pymysql://" + database_url[len("mysql://"):]
    elif database_url.startswith("mysql+mysqldb://"):
        database_url = "mysql+pymysql://" + database_url[len("mysql+mysqldb://"):]
    application.config["SQLALCHEMY_DATABASE_URI"] = database_url
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    application.config["APP_BASE_URL"] = (os.getenv("APP_BASE_URL") or "").rstrip("/")
    application.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY") or application.config["SECRET_KEY"]
    application.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    application.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    application.config["JWT_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    application.config["JWT_COOKIE_SAMESITE"] = "Lax"
    application.config["JWT_COOKIE_CSRF_PROTECT"] = True
    application.config["JWT_CSRF_CHECK_FORM"] = True

    db.init_app(application)
    jwt.init_app(application)

    def app_url(endpoint, **values):
        path = url_for(endpoint, **values)
        base_url = application.config["APP_BASE_URL"]
        return f"{base_url}{path}" if base_url else url_for(endpoint, _external=True, **values)

    def subscription_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            subscription = get_or_create_subscription(g.current_user)
            if subscription_state(subscription) == "expired":
                if request.path.startswith("/api/"):
                    return jsonify(error="Seu período de acesso terminou. Escolha um plano para continuar."), 402
                flash("Seu período de acesso terminou. Escolha um plano para continuar.", "error")
                return redirect(url_for("plans"))
            return view(*args, **kwargs)
        return wrapped

    def find_request_user():
        identity = get_jwt_identity()
        if identity is None:
            return None
        try:
            return user_dao.get_by_id(int(identity))
        except (TypeError, ValueError):
            return None

    @application.before_request
    def load_authenticated_user():
        g.current_user = None
        if not request.cookies.get("access_token_cookie"):
            return None
        try:
            verify_jwt_in_request(optional=True)
            g.current_user = find_request_user()
        except Exception:
            # Protected routes below validate again and return the proper auth error.
            return None
        if get_jwt_identity() is not None and g.current_user is None:
            response = redirect(url_for("login"))
            unset_jwt_cookies(response)
            return response

    @application.context_processor
    def inject_template_auth():
        csrf_token = None
        if getattr(g, "current_user", None) is not None:
            try:
                csrf_token = get_jwt().get("csrf")
            except RuntimeError:
                pass
        return {"current_user": getattr(g, "current_user", None), "csrf_token": csrf_token}

    def auth_error(message):
        if request.path.startswith("/api/"):
            return jsonify(error=message), 401
        return redirect(url_for("login"))

    @jwt.unauthorized_loader
    def missing_token(_reason):
        return auth_error("Entre na sua conta para continuar.")

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return auth_error("Sua sessão expirou. Entre novamente.")

    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_payload):
        return auth_error("Sua sessão expirou. Entre novamente.")

    @application.after_request
    def refresh_active_access_token(response):
        if getattr(g, "clear_auth_cookies", False):
            return response
        if getattr(g, "current_user", None) is None:
            return response
        try:
            expires_at = get_jwt().get("exp", 0)
        except RuntimeError:
            return response
        seconds_left = expires_at - datetime.now(timezone.utc).timestamp()
        if 0 < seconds_left < 300:
            token = create_access_token(identity=str(g.current_user.id))
            set_access_cookies(response, token)
        return response

    @application.route("/")
    def home():
        return redirect(url_for("dashboard" if g.current_user else "login"))

    @application.route("/register", methods=["GET", "POST"])
    def register():
        if g.current_user:
            if request.args.get("next") == "checkout":
                return redirect(url_for("billing_checkout", plan_id="plus"))
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            user, error = user_controller.register(
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
            if error:
                flash(error, "error")
            else:
                get_or_create_subscription(user)
                destination = "billing_checkout" if request.args.get("next") == "checkout" else "dashboard"
                response = redirect(url_for(destination, **({"plan_id": "plus"} if destination == "billing_checkout" else {})))
                set_access_cookies(response, create_access_token(identity=str(user.id)))
                return response
        return render_template("auth.html", mode="register")

    @application.route("/login", methods=["GET", "POST"])
    def login():
        if g.current_user:
            if request.args.get("next") == "checkout":
                return redirect(url_for("billing_checkout", plan_id="plus"))
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            user = user_controller.authenticate(
                request.form.get("email", ""), request.form.get("password", "")
            )
            if user:
                destination = "billing_checkout" if request.args.get("next") == "checkout" else "dashboard"
                response = redirect(url_for(destination, **({"plan_id": "plus"} if destination == "billing_checkout" else {})))
                set_access_cookies(response, create_access_token(identity=str(user.id)))
                return response
            flash("E-mail ou senha incorretos.", "error")
        return render_template("auth.html", mode="login")

    @application.route("/plans")
    def plans():
        subscription = get_or_create_subscription(g.current_user) if g.current_user else None
        state = subscription_state(subscription) if subscription else "expired"
        trial_days_left = 0
        if state == "trialing" and subscription.trial_ends_at:
            trial_days_left = max(0, (subscription.trial_ends_at - datetime.utcnow()).days)
        return render_template(
            "plans.html",
            plans=PLANS,
            current_plan=subscription.plan_id if subscription else "free",
            subscription_state=state,
            trial_days_left=trial_days_left,
        )

    @application.route("/planning", methods=["GET", "POST"])
    @jwt_required()
    @subscription_required
    def planning():
        if request.method == "POST":
            section = request.form.get("section")
            if section == "daily":
                focus_task_id = request.form.get("focus_task_id") or None
                if focus_task_id:
                    try:
                        focus_task_id = int(focus_task_id)
                    except ValueError:
                        flash("Escolha uma tarefa válida.", "error")
                        return redirect(url_for("planning"))
                    if not Task.query.filter_by(id=focus_task_id, user_id=g.current_user.id).first():
                        flash("Escolha uma tarefa válida.", "error")
                        return redirect(url_for("planning"))
                planning_service.save_daily_plan(
                    g.current_user.id,
                    request.form.get("intention", ""),
                    focus_task_id,
                    request.form.get("reflection", ""),
                )
                flash("Seu plano do dia foi salvo.", "success")
            elif section == "weekly":
                planning_service.save_weekly_review(
                    g.current_user.id,
                    request.form.get("wins", ""),
                    request.form.get("blockers", ""),
                    request.form.get("next_week", ""),
                )
                flash("Sua revisão da semana foi salva.", "success")
            else:
                flash("Não foi possível identificar o formulário.", "error")
            return redirect(url_for("planning"))
        return render_template(
            "planning.html",
            daily=planning_service.get_daily_plan(g.current_user.id),
            weekly=planning_service.get_weekly_review(g.current_user.id),
            tasks=task_controller.list_tasks(g.current_user.id),
        )

    @application.route("/billing")
    @jwt_required()
    def billing():
        subscription = get_or_create_subscription(g.current_user)
        state = subscription_state(subscription)
        trial_days_left = max(0, (subscription.trial_ends_at - datetime.utcnow()).days) if state == "trialing" and subscription.trial_ends_at else 0
        return render_template(
            "billing.html",
            subscription=subscription,
            subscription_state=state,
            trial_days_left=trial_days_left,
            plan=PLANS.get(subscription.plan_id, PLANS["free"]),
        )

    @application.route("/billing/checkout/<plan_id>", methods=["GET", "POST"])
    @jwt_required()
    def billing_checkout(plan_id):
        if plan_id != "plus":
            return redirect(url_for("plans"))
        subscription = get_or_create_subscription(g.current_user)
        if subscription_state(subscription) == "active":
            flash("Você já tem uma assinatura ativa do Daymark Plus.", "success")
            return redirect(url_for("billing"))
        required_stripe_settings = ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_PLUS")
        missing_stripe_settings = [
            name for name in required_stripe_settings if not (os.getenv(name) or "").strip()
        ]
        price_id = (os.getenv("STRIPE_PRICE_PLUS") or "").strip()
        stripe_ready = not missing_stripe_settings
        if request.method == "POST" and stripe_ready:
            try:
                session = stripe_service.create_checkout_session(
                    g.current_user,
                    subscription,
                    price_id,
                    app_url("checkout_success") + "?session_id={CHECKOUT_SESSION_ID}",
                    app_url("plans"),
                )
                subscription.stripe_checkout_session_id = session.id
                db.session.commit()
                return redirect(session.url, code=303)
            except stripe_service.StripeNotConfigured:
                flash("O checkout do Stripe ainda não está configurado.", "error")
            except Exception:
                application.logger.exception("Falha ao iniciar checkout Stripe")
                flash("Não foi possível iniciar o checkout agora.", "error")
        return render_template(
            "checkout.html",
            plan=PLANS["plus"],
            stripe_ready=stripe_ready,
            missing_stripe_settings=missing_stripe_settings,
            trial_ends_at=subscription.trial_ends_at if subscription.status == "trialing" else None,
            price_env_name="STRIPE_PRICE_PLUS",
        )

    @application.route("/billing/portal", methods=["POST"])
    @jwt_required()
    def billing_portal():
        subscription = Subscription.query.filter_by(user_id=g.current_user.id).first()
        if not subscription or not subscription.stripe_customer_id:
            flash("Não há uma cobrança Stripe vinculada a esta conta.", "error")
            return redirect(url_for("billing"))
        try:
            session = stripe_service.create_portal_session(
                subscription.stripe_customer_id, app_url("billing")
            )
            return redirect(session.url, code=303)
        except Exception:
            application.logger.exception("Falha ao abrir o portal Stripe")
            flash("Não foi possível abrir o portal de cobrança agora.", "error")
            return redirect(url_for("billing"))

    @application.route("/billing/checkout/success")
    @jwt_required()
    def checkout_success():
        session_id = request.args.get("session_id", "")
        if session_id:
            try:
                session = stripe_service.retrieve_checkout_session(session_id)
                owner_id = stripe_service.stripe_attr(session, "client_reference_id")
                metadata = stripe_service.stripe_attr(session, "metadata", {})
                metadata_owner = stripe_service.stripe_attr(metadata, "user_id")
                if str(owner_id or metadata_owner or "") != str(g.current_user.id):
                    return redirect(url_for("billing"))
            except Exception:
                application.logger.exception("Não foi possível confirmar a sessão de checkout")
        return render_template("checkout_success.html")

    @application.post("/stripe/webhook")
    def stripe_webhook():
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            return jsonify(error="Stripe webhook is not configured."), 503
        try:
            event_result = stripe_service.verify_and_process_webhook(
                request.get_data(), request.headers.get("Stripe-Signature", ""), webhook_secret
            )
            return jsonify(received=True, event=event_result[0])
        except Exception:
            application.logger.exception("Stripe webhook could not be processed")
            return jsonify(error="Invalid Stripe webhook."), 400

    @application.post("/logout")
    @jwt_required()
    def logout():
        g.clear_auth_cookies = True
        response = redirect(url_for("login"))
        unset_jwt_cookies(response)
        return response

    @application.route("/dashboard")
    @jwt_required()
    @subscription_required
    def dashboard():
        view_data = task_controller.get_dashboard_data(g.current_user.id)
        subscription = get_or_create_subscription(g.current_user)
        state = subscription_state(subscription)
        view_data["subscription_state"] = state
        view_data["trial_days_left"] = max(0, (subscription.trial_ends_at - datetime.utcnow()).days) if state == "trialing" and subscription.trial_ends_at else 0
        return render_template("dashboard.html", **view_data)

    @application.route("/metrics")
    @jwt_required()
    @subscription_required
    def metrics():
        metrics_data = task_controller.get_metrics(g.current_user.id)
        return render_template("metrics.html", metrics=metrics_data)

    @application.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @jwt_required()
    @subscription_required
    def edit_task(task_id):
        task = task_controller.get_task_for_edit(task_id, g.current_user.id)
        if request.method == "POST":
            updated_task, error = task_controller.update_task(
                task_id,
                g.current_user.id,
                request.form.get("title", ""),
                request.form.get("due_date", ""),
                request.form.get("notes", ""),
                request.form.get("priority", "medium"),
            )
            if error:
                flash(error, "error")
            else:
                task = updated_task
                flash("Tarefa atualizada.", "success")
                return redirect(url_for("dashboard"))
        return render_template("edit_task.html", task=task)

    @application.route("/tasks/<int:task_id>/breakdown", methods=["GET", "POST"])
    @jwt_required()
    @subscription_required
    def breakdown_task(task_id):
        task = task_controller.get_task_for_edit(task_id, g.current_user.id)
        if request.method == "POST":
            titles = [line.strip() for line in request.form.get("steps", "").splitlines() if line.strip()]
            task_dao.add_steps(task, titles)
            flash("As etapas da tarefa foram salvas.", "success")
            return redirect(url_for("breakdown_task", task_id=task.id))
        return render_template("breakdown.html", task=task)

    @application.post("/tasks/<int:task_id>/steps/suggest")
    @jwt_required()
    @subscription_required
    def suggest_task_steps(task_id):
        task = task_controller.get_task_for_edit(task_id, g.current_user.id)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify(error="O assistente ainda não está configurado."), 503
        try:
            response = OpenAI(api_key=api_key).responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions="Responda sempre em português do Brasil, com uma ação curta por linha e sem numeração.",
                input=f"Divida esta tarefa em etapas práticas e pequenas: {task.title}\n{task.notes}",
            )
            steps = [line.strip(" -*\t") for line in response.output_text.splitlines() if line.strip()]
            return jsonify(steps=steps)
        except Exception:
            application.logger.exception("Falha ao sugerir etapas da tarefa")
            return jsonify(error="Não foi possível sugerir etapas agora."), 502

    @application.post("/tasks/<int:task_id>/steps/<int:step_id>/toggle")
    @jwt_required()
    @subscription_required
    def toggle_task_step(task_id, step_id):
        task = task_controller.get_task_for_edit(task_id, g.current_user.id)
        step = next((item for item in task.steps if item.id == step_id), None)
        if step is None:
            return "Not found", 404
        task_dao.toggle_step(step)
        return redirect(url_for("breakdown_task", task_id=task.id))

    @application.post("/tasks")
    @jwt_required()
    @subscription_required
    def create_task():
        _, error = task_controller.add_task(
            g.current_user.id,
            request.form.get("title", ""),
            request.form.get("due_date", ""),
            request.form.get("notes", ""),
            request.form.get("priority", "medium"),
        )
        if error:
            flash(error, "error")
        else:
            flash("Tarefa adicionada à sua lista.", "success")
        return redirect(url_for("dashboard"))

    @application.post("/tasks/<int:task_id>/toggle")
    @jwt_required()
    @subscription_required
    def toggle_task(task_id):
        task_controller.toggle_task(task_id, g.current_user.id)
        return redirect(url_for("dashboard"))

    @application.post("/tasks/<int:task_id>/delete")
    @jwt_required()
    @subscription_required
    def delete_task(task_id):
        task_controller.remove_task(task_id, g.current_user.id)
        flash("Tarefa excluída.", "success")
        return redirect(url_for("dashboard"))

    @application.route("/profile", methods=["GET", "POST"])
    @jwt_required()
    def profile():
        if request.method == "POST":
            error = user_controller.update_profile(
                g.current_user,
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
            )
            if error:
                flash(error, "error")
            else:
                flash("As configurações da sua conta foram atualizadas.", "success")
                return redirect(url_for("profile"))
        return render_template("profile.html")

    @application.post("/profile/delete")
    @jwt_required()
    def delete_account():
        user = g.current_user
        if not user.check_password(request.form.get("password", "")):
            flash("Sua conta não foi excluída. A senha está incorreta.", "error")
            return redirect(url_for("profile"))
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        try:
            if subscription and subscription.stripe_checkout_session_id:
                stripe_service.close_checkout_session(subscription.stripe_checkout_session_id)
            if subscription and subscription.stripe_subscription_id:
                stripe_service.cancel_stripe_subscription(subscription.stripe_subscription_id)
        except Exception:
            application.logger.exception("Não foi possível encerrar a assinatura antes da exclusão")
            flash("Sua conta não foi excluída porque não foi possível confirmar o cancelamento no Stripe. Tente novamente.", "error")
            return redirect(url_for("profile"))
        if not user_controller.delete_account(user, request.form.get("password", "")):
            flash("Não foi possível excluir sua conta agora.", "error")
            return redirect(url_for("profile"))
        flash("Sua conta e suas tarefas foram excluídas.", "success")
        g.clear_auth_cookies = True
        response = redirect(url_for("login"))
        unset_jwt_cookies(response)
        return response

    @application.post("/api/chat")
    @jwt_required()
    @subscription_required
    def chat():
        data = request.get_json(silent=True) or {}
        message = str(data.get("message", "")).strip()
        if not message:
            return jsonify(error="Escreva uma mensagem primeiro."), 400
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify(error="O assistente ainda não está configurado. Adicione OPENAI_API_KEY ao arquivo .env."), 503

        task_list = task_controller.task_context(g.current_user.id)
        task_context = "\n".join(
            f"- [{'concluída' if task.completed else 'pendente'}] {task.title}" for task in task_list
        ) or "Nenhuma tarefa por enquanto."
        try:
            response = OpenAI(api_key=api_key).responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=(
                    "Você é um assistente de planejamento objetivo e acolhedor. Responda sempre em português do Brasil. "
                    "Ajude a organizar tarefas e sugerir próximos passos práticos. Você pode conversar sobre a lista, "
                    "mas não pode alterá-la.\n\nTarefas atuais:\n" + task_context
                ),
                input=message,
            )
            return jsonify(reply=response.output_text)
        except Exception:
            application.logger.exception("Falha ao consultar a API da OpenAI")
            return jsonify(error="O assistente não conseguiu responder agora. Tente novamente."), 502

    with application.app_context():
        db.create_all()
        task_columns = {column["name"] for column in inspect(db.engine).get_columns("task")}
        if "completed_at" not in task_columns:
            dialect = db.engine.dialect.name
            if dialect == "postgresql":
                db.session.execute(text("ALTER TABLE task ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP"))
            else:
                column_type = db.DateTime().compile(dialect=db.engine.dialect)
                db.session.execute(text(f"ALTER TABLE task ADD COLUMN completed_at {column_type}"))
            db.session.commit()

    return application


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
