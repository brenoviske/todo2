"""Task business rules. HTTP routes stay in app.py."""
from datetime import date, datetime, timedelta

from tasks import dao

VALID_PRIORITIES = {"low", "medium", "high"}


def list_tasks(user_id):
    return dao.list_for_user(user_id)


def get_dashboard_data(user_id):
    tasks = dao.list_for_user(user_id)
    return {
        "tasks": tasks,
        "active_count": sum(not task.completed for task in tasks),
        "done_count": sum(task.completed for task in tasks),
    }


def add_task(user_id, title, due_date, notes="", priority="medium"):
    title = title.strip()
    if not title:
        return None, "Dê um nome para sua tarefa."
    if priority not in VALID_PRIORITIES:
        return None, "Escolha uma prioridade válida."
    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            return None, "Escolha um prazo válido."
    return dao.create(user_id, title, parsed_due_date, notes.strip(), priority), None


def get_task_for_edit(task_id, user_id):
    return dao.get_for_user(task_id, user_id)


def update_task(task_id, user_id, title, due_date, notes, priority):
    task = dao.get_for_user(task_id, user_id)
    title = title.strip()
    if not title:
        return None, "Dê um nome para sua tarefa."
    if priority not in VALID_PRIORITIES:
        return None, "Escolha uma prioridade válida."
    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            return None, "Escolha um prazo válido."
    return dao.update(task, title, parsed_due_date, notes.strip(), priority), None


def toggle_task(task_id, user_id):
    task = dao.get_for_user(task_id, user_id)
    task.completed = not task.completed
    return dao.save(task)


def remove_task(task_id, user_id):
    task = dao.get_for_user(task_id, user_id)
    dao.delete(task)


def task_context(user_id, limit=40):
    return dao.list_for_chat(user_id, limit)


def get_metrics(user_id):
    """Build the dashboard analytics from the signed-in user's tasks."""
    tasks = dao.list_for_user(user_id)
    today = date.today()
    completed = [task for task in tasks if task.completed]
    pending = [task for task in tasks if not task.completed]
    total = len(tasks)

    days = [today - timedelta(days=offset) for offset in reversed(range(7))]
    daily_counts = [
        {"date": day.isoformat(), "count": sum(task.created_at.date() == day for task in tasks)}
        for day in days
    ]
    peak = max((item["count"] for item in daily_counts), default=0)
    for item in daily_counts:
        item["height"] = max(6, round(item["count"] / peak * 100)) if peak and item["count"] else 0

    overdue = [task for task in pending if task.due_date and task.due_date < today]
    upcoming = sorted(
        (task for task in pending if task.due_date and today <= task.due_date <= today + timedelta(days=7)),
        key=lambda task: task.due_date,
    )[:5]

    return {
        "total": total,
        "completed": len(completed),
        "pending": len(pending),
        "overdue": len(overdue),
        "completion_percent": round(len(completed) / total * 100) if total else 0,
        "weekly_created": sum(item["count"] for item in daily_counts),
        "daily_activity": daily_counts,
        "upcoming": upcoming,
    }
