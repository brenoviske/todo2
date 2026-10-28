"""Server-side Stripe operations and subscription synchronization."""
import os
from datetime import datetime, timezone

from extensions import db
from users.billing import Subscription, StripeWebhookEvent
from users.model import User


class StripeNotConfigured(Exception):
    pass


def get_stripe_module_and_client():
    import stripe

    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not configured")
    return stripe, stripe.StripeClient(secret_key, max_network_retries=2)


def create_checkout_session(user, subscription, price_id, success_url, cancel_url):
    _stripe, client = get_stripe_module_and_client()
    subscription_data = {"metadata": {"user_id": str(user.id), "plan_id": "plus"}}
    if subscription.status == "trialing" and subscription.trial_ends_at:
        trial_ends_at = subscription.trial_ends_at.replace(tzinfo=timezone.utc)
        if trial_ends_at > datetime.now(timezone.utc):
            subscription_data["trial_end"] = int(trial_ends_at.timestamp())
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id), "plan_id": "plus"},
        "subscription_data": subscription_data,
    }
    if subscription.stripe_customer_id:
        params["customer"] = subscription.stripe_customer_id
    else:
        params["customer_email"] = user.email
    return client.v1.checkout.sessions.create(params=params)


def create_portal_session(customer_id, return_url):
    _stripe, client = get_stripe_module_and_client()
    return client.v1.billing_portal.sessions.create(
        params={"customer": customer_id, "return_url": return_url}
    )


def retrieve_checkout_session(session_id):
    if not session_id:
        return None
    _stripe, client = get_stripe_module_and_client()
    return client.v1.checkout.sessions.retrieve(session_id)


def close_checkout_session(session_id):
    """Expire an open checkout or cancel a subscription completed before deletion."""
    if not session_id:
        return
    _stripe, client = get_stripe_module_and_client()
    session = client.v1.checkout.sessions.retrieve(session_id)
    status = stripe_attr(session, "status")
    if status == "open":
        client.v1.checkout.sessions.expire(session_id)
    elif status == "complete":
        subscription_id = stripe_attr(session, "subscription")
        subscription_id = stripe_attr(subscription_id, "id", subscription_id)
        if subscription_id:
            cancel_stripe_subscription(subscription_id)


def cancel_stripe_subscription(subscription_id):
    """Cancel immediately so account deletion cannot leave future renewals active."""
    if not subscription_id:
        return
    _stripe, client = get_stripe_module_and_client()
    remote = client.v1.subscriptions.retrieve(subscription_id)
    if stripe_attr(remote, "status") not in {"canceled", "incomplete_expired"}:
        client.v1.subscriptions.cancel(subscription_id)


def stripe_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def sync_subscription(stripe_subscription, fallback_user_id=None):
    """Update local access from a verified Stripe subscription snapshot."""
    stripe_subscription_id = stripe_attr(stripe_subscription, "id")
    customer = stripe_attr(stripe_subscription, "customer")
    customer_id = stripe_attr(customer, "id", customer)
    metadata = stripe_attr(stripe_subscription, "metadata", {})
    metadata_user_id = stripe_attr(metadata, "user_id")
    user_id = metadata_user_id or fallback_user_id

    local = None
    if stripe_subscription_id:
        local = Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
    if local is None and customer_id:
        local = Subscription.query.filter_by(stripe_customer_id=customer_id).first()
    if local is None and user_id:
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            user = None
        if user:
            local = Subscription.query.filter_by(user_id=user.id).first()
            if local is None:
                local = Subscription(user_id=user.id, plan_id="plus", status="incomplete")
                db.session.add(local)
    if local is None:
        return False

    status = stripe_attr(stripe_subscription, "status", "incomplete")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    trial_still_valid = (
        local.status == "trialing"
        and local.trial_ends_at is not None
        and local.trial_ends_at > now
    )
    local.plan_id = "plus"
    local.stripe_customer_id = customer_id or local.stripe_customer_id
    local.stripe_subscription_id = stripe_subscription_id or local.stripe_subscription_id
    local.stripe_checkout_session_id = None
    local.status = "active" if status == "active" else ("trialing" if trial_still_valid else status)

    period_end = stripe_attr(stripe_subscription, "current_period_end")
    if period_end:
        local.current_period_end = datetime.fromtimestamp(int(period_end), tz=timezone.utc).replace(tzinfo=None)
    items = stripe_attr(stripe_attr(stripe_subscription, "items", {}), "data", []) or []
    if items:
        price = stripe_attr(items[0], "price")
        local.stripe_price_id = stripe_attr(price, "id", local.stripe_price_id)
    return True


def verify_and_process_webhook(payload, signature, webhook_secret):
    import stripe

    event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    event_type = stripe_attr(event, "type", "")
    event_id = stripe_attr(event, "id")
    if not event_id:
        raise ValueError("Stripe event is missing its ID")
    if db.session.get(StripeWebhookEvent, event_id) is not None:
        return event_type, True
    data = stripe_attr(event, "data", {})
    obj = stripe_attr(data, "object", {})

    if event_type == "checkout.session.completed":
        if stripe_attr(obj, "mode") == "subscription":
            subscription_id = stripe_attr(obj, "subscription")
            subscription_id = stripe_attr(subscription_id, "id", subscription_id)
            if subscription_id:
                _stripe, client = get_stripe_module_and_client()
                remote_subscription = client.v1.subscriptions.retrieve(subscription_id)
                linked = sync_subscription(remote_subscription, stripe_attr(obj, "client_reference_id"))
                if not linked:
                    cancel_stripe_subscription(subscription_id)
    elif event_type.startswith("customer.subscription."):
        subscription_id = stripe_attr(obj, "id")
        if subscription_id:
            _stripe, client = get_stripe_module_and_client()
            remote_subscription = client.v1.subscriptions.retrieve(subscription_id)
            sync_subscription(remote_subscription)
    elif event_type in {"invoice.paid", "invoice.payment_failed"}:
        subscription_id = stripe_attr(obj, "subscription")
        if not subscription_id:
            parent = stripe_attr(obj, "parent", {})
            details = stripe_attr(parent, "subscription_details", {})
            subscription_id = stripe_attr(details, "subscription")
        subscription_id = stripe_attr(subscription_id, "id", subscription_id)
        if subscription_id:
            _stripe, client = get_stripe_module_and_client()
            remote_subscription = client.v1.subscriptions.retrieve(subscription_id)
            sync_subscription(remote_subscription)
    db.session.add(StripeWebhookEvent(event_id=event_id, event_type=event_type))
    db.session.commit()
    return event_type, False
