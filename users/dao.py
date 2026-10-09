from extensions import db
from users.model import User


def get_by_id(user_id):
    return db.session.get(User, user_id)


def get_by_email(email):
    return User.query.filter_by(email=email).first()


def email_in_use(email, except_user_id=None):
    query = User.query.filter_by(email=email)
    if except_user_id is not None:
        query = query.filter(User.id != except_user_id)
    return query.first() is not None


def create(name, email, password):
    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def save(user):
    db.session.commit()
    return user


def delete(user):
    db.session.delete(user)
    db.session.commit()
