from __future__ import annotations

import sqlite3
from dataclasses import dataclass


STATUS_LABELS = {
    "new": "новая",
    "analyzed": "проанализирована",
    "draft": "черновик",
    "sent": "отправлен",
    "waiting": "ожидание",
    "followed_up": "follow-up отправлен",
}

CHANCE_LABELS = {
    "high": "высокие",
    "medium": "средние",
    "low": "низкие",
    "skip": "пропустить",
    None: "-",
}


@dataclass(frozen=True)
class TodaySummary:
    due_followups: list[sqlite3.Row]
    unsent_applications: list[sqlite3.Row]
    vacancies_without_applications: list[sqlite3.Row]


def format_today_summary(summary: TodaySummary, *, today: str) -> str:
    lines = [f"Сегодня: {today}", ""]

    total_actions = (
        len(summary.due_followups)
        + len(summary.unsent_applications)
        + len(summary.vacancies_without_applications)
    )
    if total_actions == 0:
        return "\n".join(
            [
                f"Сегодня: {today}",
                "",
                "Активных задач нет.",
                "Рекомендация: добавьте новую вакансию через пункт 2 или команду paste.",
            ]
        )

    lines.append("Что требует внимания:")
    if summary.due_followups:
        lines.append("")
        lines.append("Follow-up:")
        for row in summary.due_followups:
            lines.append(
                f"- Отклик #{row['id']} | до {row['next_followup_at']} | "
                f"{row['vacancy_title']} | {row['company'] or '-'}"
            )

    if summary.unsent_applications:
        lines.append("")
        lines.append("Отклики без отправки:")
        for row in summary.unsent_applications:
            state = _application_state(row)
            lines.append(
                f"- Отклик #{row['id']} | {state} | {row['vacancy_title']} | "
                f"{row['company'] or '-'} | шанс: {_chance_label(row['chance'])}"
            )

    if summary.vacancies_without_applications:
        lines.append("")
        lines.append("Вакансии без отклика:")
        for row in summary.vacancies_without_applications:
            lines.append(
                f"- Вакансия #{row['id']} | {_status_label(row['status'])} | "
                f"{row['title']} | {row['company'] or '-'} | шанс: {_chance_label(row['chance'])}"
            )

    recommendation = _recommendation(summary)
    lines.append("")
    lines.append(f"Рекомендуемый следующий шаг: {recommendation}")
    return "\n".join(lines)


def _application_state(row: sqlite3.Row) -> str:
    if not row["generated_text"] and not row["final_text"]:
        return "нет текста"
    if not row["user_approved"]:
        return "нужно проверить и одобрить"
    return "одобрен, можно отметить отправку"


def _recommendation(summary: TodaySummary) -> str:
    if summary.due_followups:
        row = summary.due_followups[0]
        return f"сделайте follow-up по отклику #{row['id']}."

    for row in summary.unsent_applications:
        if not row["generated_text"] and not row["final_text"]:
            return f"пересоздайте черновик для отклика #{row['id']} через пункт 9."
        if not row["user_approved"]:
            return f"проверьте отклик #{row['id']} через пункт 12 и затем одобрите."
        return f"отметьте отклик #{row['id']} отправленным через пункт 14."

    if summary.vacancies_without_applications:
        row = summary.vacancies_without_applications[0]
        return f"создайте черновик для вакансии #{row['id']} через пункт 8."

    return "добавьте новую вакансию через пункт 2."


def _status_label(value: str | None) -> str:
    return STATUS_LABELS.get(value, value or "-")


def _chance_label(value: str | None) -> str:
    return CHANCE_LABELS.get(value, value or "-")
