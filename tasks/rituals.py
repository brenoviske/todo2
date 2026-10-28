from datetime import date

from extensions import db


class DailyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_date = db.Column(db.Date, nullable=False)
    intention = db.Column(db.String(500), default="", nullable=False)
    focus_task_id = db.Column(db.Integer, db.ForeignKey("task.id", ondelete="SET NULL"), nullable=True)
    reflection = db.Column(db.Text, default="", nullable=False)
    owner = db.relationship("User", back_populates="daily_plans")
    __table_args__ = (db.UniqueConstraint("user_id", "plan_date", name="uq_daily_plan_user_date"),)


class WeeklyReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False)
    wins = db.Column(db.Text, default="", nullable=False)
    blockers = db.Column(db.Text, default="", nullable=False)
    next_week = db.Column(db.Text, default="", nullable=False)
    owner = db.relationship("User", back_populates="weekly_reviews")
    __table_args__ = (db.UniqueConstraint("user_id", "week_start", name="uq_weekly_review_user_week"),)


def monday_of(day=None):
    day = day or date.today()
    return day.fromordinal(day.toordinal() - day.weekday())
