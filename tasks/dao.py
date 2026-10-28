from extensions import db
from tasks.model import Task, TaskStep


def list_for_user(user_id):
    return Task.query.filter_by(user_id=user_id).order_by(Task.completed.asc(), Task.created_at.desc()).all()


def list_for_chat(user_id, limit=40):
    return Task.query.filter_by(user_id=user_id).order_by(Task.completed.asc()).limit(limit).all()


def get_for_user(task_id, user_id):
    return Task.query.filter_by(id=task_id, user_id=user_id).first_or_404()


def create(user_id, title, due_date=None, notes="", priority="medium"):
    task = Task(user_id=user_id, title=title, due_date=due_date, notes=notes, priority=priority)
    db.session.add(task)
    db.session.commit()
    return task


def save(task):
    db.session.commit()
    return task


def update(task, title, due_date, notes, priority):
    task.title = title
    task.due_date = due_date
    task.notes = notes
    task.priority = priority
    db.session.commit()
    return task


def delete(task):
    db.session.delete(task)
    db.session.commit()


def add_steps(task, titles):
    task.steps.clear()
    for position, title in enumerate(titles):
        task.steps.append(TaskStep(title=title, position=position))
    db.session.commit()


def toggle_step(step):
    step.completed = not step.completed
    db.session.commit()
    return step
