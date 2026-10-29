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
    task.completed_at = datetime.utcnow() if task.completed else None
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
    pending_on_time = len(pending) - len(overdue)
    upcoming = sorted(
        (task for task in pending if task.due_date and today <= task.due_date <= today + timedelta(days=7)),
        key=lambda task: task.due_date,
    )[:5]

    current_month_start = date(today.year, today.month, 1)
    next_month_start = (
        date(today.year + 1, 1, 1)
        if today.month == 12
        else date(today.year, today.month + 1, 1)
    )
    previous_month_start = (
        date(today.year - 1, 12, 1)
        if today.month == 1
        else date(today.year, today.month - 1, 1)
    )

    def in_month(day, start, end):
        return day is not None and start <= day < end

    def month_summary(start, end):
        completed_in_month = sum(
            task.completed and task.completed_at is not None
            and in_month(task.completed_at.date(), start, end)
            for task in tasks
        )
        pending_from_month = sum(
            not task.completed
            and in_month(task.created_at.date(), start, end)
            and not (task.due_date and task.due_date < today)
            for task in tasks
        )
        overdue_in_month = sum(
            task.due_date is not None
            and in_month(task.due_date, start, end)
            and task.due_date < today
            and (not task.completed or (task.completed_at and task.completed_at.date() > task.due_date))
            for task in tasks
        )
        return {
            "completed": completed_in_month,
            "pending": pending_from_month,
            "overdue": overdue_in_month,
        }

    current_month = month_summary(current_month_start, next_month_start)
    previous_month = month_summary(previous_month_start, current_month_start)
    month_comparison = {
        "current_label": current_month_start.strftime("%m/%Y"),
        "previous_label": previous_month_start.strftime("%m/%Y"),
        "current": current_month,
        "previous": previous_month,
        "changes": {
            key: current_month[key] - previous_month[key]
            for key in current_month
        },
    }

    return {
        "total": total,
        "completed": len(completed),
        "pending": len(pending),
        "overdue": len(overdue),
        "pending_on_time": pending_on_time,
        "completed_share": round(len(completed) / total * 100) if total else 0,
        "pending_share": round(pending_on_time / total * 100) if total else 0,
        "overdue_share": round(len(overdue) / total * 100) if total else 0,
        "completion_percent": round(len(completed) / total * 100) if total else 0,
        "weekly_created": sum(item["count"] for item in daily_counts),
        "daily_activity": daily_counts,
        "upcoming": upcoming,
        "month_comparison": month_comparison,
    }
