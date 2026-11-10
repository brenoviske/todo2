"""User account business rules. HTTP routes stay in app.py."""
import re

from users import dao


COMMON_PASSWORDS = {"password123!", "qwerty123456!", "letmein12345!", "welcome12345!"}


def password_strength(password):
    """Return a 0–4 strength score shared by signup and password changes."""
    if not password:
        return 0
    classes = sum(bool(pattern.search(password)) for pattern in (
        re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"[0-9]"), re.compile(r"[^A-Za-z0-9]"),
    ))
    score = min(4, (len(password) >= 8) + (len(password) >= 12) + (classes >= 2) + (classes >= 3))
    if password.lower() in COMMON_PASSWORDS or len(set(password)) <= 2:
        return min(score, 1)
    return score


def password_is_strong(password):
    return len(password) >= 12 and password_strength(password) == 4


def register(name, email, password, confirm_password=None):
    name, email = name.strip(), email.strip().lower()
    if not name or not email:
        return None, "Informe seu nome e e-mail."
    if confirm_password is not None and password != confirm_password:
        return None, "As senhas não coincidem."
    if not password_is_strong(password):
        return None, "Sua senha precisa ser forte: use pelo menos 12 caracteres e combine letras, números e símbolos."
    if dao.email_in_use(email):
        return None, "Esse e-mail já está cadastrado. Tente entrar na sua conta."
    return dao.create(name, email, password), None


def authenticate(email, password):
    user = dao.get_by_email(email.strip().lower())
    return user if user and user.check_password(password) else None


def update_profile(user, name, email, current_password, new_password):
    name, email = name.strip(), email.strip().lower()
    if not name or not email:
        return "Nome e e-mail são obrigatórios."
    if dao.email_in_use(email, except_user_id=user.id):
        return "Esse e-mail já está sendo usado."
    if new_password and not user.check_password(current_password):
        return "Para trocar sua senha, informe a senha atual corretamente."
    if new_password and not password_is_strong(new_password):
        return "A nova senha precisa ser forte: use pelo menos 12 caracteres e combine letras, números e símbolos."
    user.name, user.email = name, email
    if new_password:
        user.set_password(new_password)
    dao.save(user)
    return None


def delete_account(user, password):
    if not user.check_password(password):
        return False
    dao.delete(user)
    return True
