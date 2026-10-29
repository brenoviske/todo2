from datetime import datetime, timedelta

from extensions import db


PLANS = {
    "free": {
        "name": "Teste grátis",
        "price": "R$ 0",
        "cadence": "por 1 semana",
        "description": "Conheça o Daymark com acesso completo antes de escolher continuar.",
        "features": ["Acesso completo durante o teste", "Sem cobrança automática", "Acesso pausa após 1 semana se não assinar"],
    },
    "plus": {
        "name": "Daymark Plus",
        "price": "R$ 80",
        "cadence": "mensal",
        "description": "Experimente tudo por uma semana. Depois, continue por R$ 80 ao mês.",
        "features": ["1 semana grátis", "Tudo do período de avaliação", "Assistente de planejamento com IA", "Sugestões para dividir tarefas"],
    },
}

TRIAL_DURATION = timedelta(weeks=1)


def get_or_create_subscription(user):
    """Create a one-week trial for new accounts and safely onboard older accounts."""
    subscription = Subscription.query.filter_by(user_id=user.id).first()
    if subscription:
        return subscription
    trial_starts_at = datetime.utcnow()
    subscription = Subscription(
        user_id=user.id,
        plan_id="plus",
        status="trialing",
        trial_ends_at=trial_starts_at + TRIAL_DURATION,
        trial_duration_days=7,
    )
    if subscription.trial_ends_at <= datetime.utcnow():
        subscription.status = "expired"
    db.session.add(subscription)
    db.session.commit()
    return subscription


def subscription_state(subscription, now=None):
    now = now or datetime.utcnow()
    if subscription is None:
        return "expired"
    if subscription.status == "trialing":
        if subscription.trial_ends_at and subscription.trial_ends_at > now:
            return "trialing"
        subscription.status = "expired"
        db.session.commit()
        return "expired"
    if subscription.status == "active":
        if subscription.current_period_end and subscription.current_period_end > now:
            return "active"
        subscription.status = "expired"
        db.session.commit()
        return "expired"
    return "expired"


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_id = db.Column(db.String(40), nullable=False, default="free")
    status = db.Column(db.String(30), nullable=False, default="free")
    stripe_customer_id = db.Column(db.String(120), nullable=True, unique=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True, unique=True)
    stripe_checkout_session_id = db.Column(db.String(255), nullable=True)
    stripe_price_id = db.Column(db.String(120), nullable=True)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    trial_duration_days = db.Column(db.Integer, nullable=False, default=7)
    current_period_end = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    owner = db.relationship("User", back_populates="subscription")


class StripeWebhookEvent(db.Model):
    """Processed Stripe event IDs prevent duplicate deliveries applying twice."""
    event_id = db.Column(db.String(255), primary_key=True)
    event_type = db.Column(db.String(120), nullable=False)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
