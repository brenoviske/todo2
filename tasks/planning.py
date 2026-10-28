from datetime import date

from extensions import db
from tasks.rituals import DailyPlan, WeeklyReview, monday_of


def get_daily_plan(user_id, day=None):
    day = day or date.today()
    return DailyPlan.query.filter_by(user_id=user_id, plan_date=day).first()


def save_daily_plan(user_id, intention, focus_task_id, reflection, day=None):
    day = day or date.today()
    plan = get_daily_plan(user_id, day)
    if plan is None:
        plan = DailyPlan(user_id=user_id, plan_date=day)
        db.session.add(plan)
    plan.intention = intention.strip()[:500]
    plan.focus_task_id = focus_task_id
    plan.reflection = reflection.strip()
    db.session.commit()
    return plan


def get_weekly_review(user_id, day=None):
    week_start = monday_of(day)
    return WeeklyReview.query.filter_by(user_id=user_id, week_start=week_start).first()


def save_weekly_review(user_id, wins, blockers, next_week, day=None):
    week_start = monday_of(day)
    review = get_weekly_review(user_id, day)
    if review is None:
        review = WeeklyReview(user_id=user_id, week_start=week_start)
        db.session.add(review)
    review.wins = wins.strip()
    review.blockers = blockers.strip()
    review.next_week = next_week.strip()
    db.session.commit()
    return review
