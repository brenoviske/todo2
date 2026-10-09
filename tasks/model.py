from datetime import datetime

from extensions import db


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    notes = db.Column(db.Text, default="", nullable=False)
    priority = db.Column(db.String(10), default="medium", nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    owner = db.relationship("User", back_populates="tasks")
