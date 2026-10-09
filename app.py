import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
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
from sqlalchemy import inspect, text

from extensions import db
from tasks import controller as task_controller
from tasks.model import Task  # Register the model with SQLAlchemy before create_all().
from users import controller as user_controller
from users import dao as user_dao
from users.model import User  # Register the model with SQLAlchemy before create_all().

load_dotenv()

jwt = JWTManager()


def create_app():
    """Create the app and connect its HTTP routes to the domain controllers."""
    application = Flask(__name__)
    application.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    application.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///tasks.db")
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    application.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY") or application.config["SECRET_KEY"]
    application.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    application.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=15)
    application.config["JWT_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    application.config["JWT_COOKIE_SAMESITE"] = "Lax"
    application.config["JWT_COOKIE_CSRF_PROTECT"] = True
    application.config["JWT_CSRF_CHECK_FORM"] = True

    db.init_app(application)
    jwt.init_app(application)

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
                response = redirect(url_for("dashboard"))
                set_access_cookies(response, create_access_token(identity=str(user.id)))
                return response
        return render_template("auth.html", mode="register")

    @application.route("/login", methods=["GET", "POST"])
    def login():
        if g.current_user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            user = user_controller.authenticate(
                request.form.get("email", ""), request.form.get("password", "")
            )
            if user:
                response = redirect(url_for("dashboard"))
                set_access_cookies(response, create_access_token(identity=str(user.id)))
                return response
            flash("E-mail ou senha incorretos.", "error")
        return render_template("auth.html", mode="login")

    @application.post("/logout")
    @jwt_required()
    def logout():
        g.clear_auth_cookies = True
        response = redirect(url_for("login"))
        unset_jwt_cookies(response)
        return response

    @application.route("/dashboard")
    @jwt_required()
    def dashboard():
        view_data = task_controller.get_dashboard_data(g.current_user.id)
        return render_template("dashboard.html", **view_data)

    @application.route("/metrics")
    @jwt_required()
    def metrics():
        metrics_data = task_controller.get_metrics(g.current_user.id)
        return render_template("metrics.html", metrics=metrics_data)

    @application.post("/tasks")
    @jwt_required()
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

    @application.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @jwt_required()
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

    @application.post("/tasks/<int:task_id>/toggle")
    @jwt_required()
    def toggle_task(task_id):
        task_controller.toggle_task(task_id, g.current_user.id)
        return redirect(url_for("dashboard"))

    @application.post("/tasks/<int:task_id>/delete")
    @jwt_required()
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
        if not user_controller.delete_account(user, request.form.get("password", "")):
            flash("Sua conta não foi excluída. A senha está incorreta.", "error")
            return redirect(url_for("profile"))
        flash("Sua conta e suas tarefas foram excluídas.", "success")
        g.clear_auth_cookies = True
        response = redirect(url_for("login"))
        unset_jwt_cookies(response)
        return response

    @application.post("/api/chat")
    @jwt_required()
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
            f"- [{'concluída' if task.completed else 'pendente'}; prioridade { {'high': 'alta', 'medium': 'média', 'low': 'baixa'}.get(task.priority, 'média') }] {task.title}"
            + (f" — {task.notes}" if task.notes else "")
            for task in task_list
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
        if "priority" not in task_columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'medium'"))

    return application


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
