"""User account business rules. HTTP routes stay in app.py."""
from users import dao


def register(name, email, password):
    name, email = name.strip(), email.strip().lower()
    if not name or not email or len(password) < 8:
        return None, "Informe seu nome e e-mail e escolha uma senha com pelo menos 8 caracteres."
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
    if new_password and (not user.check_password(current_password) or len(new_password) < 8):
        return "Para trocar sua senha, informe a senha atual e uma nova senha com pelo menos 8 caracteres."
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
