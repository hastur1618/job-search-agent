from __future__ import annotations

import re
import sqlite3

from job_agent.profile import CandidateProfile


ROLE_LABELS = {
    "ai_automation": "AI automation",
    "outreach": "Outreach",
    "link_builder": "Link Builder",
    "ai_rater": "AI rater / annotator",
    "other": "другое направление",
    "unknown": "не определено",
}


def build_explanation(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    covered = [row for row in requirements if row["is_covered"] == 1]
    missing = [row for row in requirements if row["is_covered"] == 0]
    unknown = [row for row in requirements if row["is_covered"] is None]

    lines = [
        f"Вакансия: {vacancy['title']}",
        f"Направление: {ROLE_LABELS.get(vacancy['detected_role'], vacancy['detected_role'])}",
        f"Резюме: {vacancy['selected_resume']}",
        f"Шанс: {vacancy['chance']} (score={vacancy['match_score']})",
        "",
        "Почему так:",
        _why_role(vacancy, covered),
        _why_chance(vacancy, flags, missing, unknown, profile),
    ]

    questions = _questions_to_employer(vacancy, flags, unknown)
    if questions:
        lines.extend(["", "Что спросить у работодателя:"])
        lines.extend(f"- {question}" for question in questions)

    advice = _advice(vacancy, flags)
    lines.extend(["", f"Рекомендация: {advice}"])
    return "\n".join(line for line in lines if line is not None)


def build_quick_review(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    covered = [row for row in requirements if row["is_covered"] == 1]
    missing = [row for row in requirements if row["is_covered"] == 0]
    unknown = [row for row in requirements if row["is_covered"] is None]

    lines = [
        "",
        "Короткий разбор:",
        f"- Решение: {_decision(vacancy)}",
        f"- Почему: {_quick_reason(vacancy, flags, covered, missing, unknown, profile)}",
    ]

    focus = _response_focus(vacancy, covered)
    if focus:
        lines.append(f"- В отклике подчеркнуть: {focus}")

    risks = _quick_risks(vacancy, flags, missing)
    if risks:
        lines.append(f"- Риски: {risks}")

    questions = _questions_to_employer(vacancy, flags, unknown)
    if questions:
        lines.append(f"- Спросить: {questions[0]}")

    next_step = _next_step(vacancy)
    lines.append(f"- Следующий шаг: {next_step}")
    return "\n".join(lines)


def build_vacancy_card(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    covered = [row for row in requirements if row["is_covered"] == 1]
    missing = [row for row in requirements if row["is_covered"] == 0]
    unknown = [row for row in requirements if row["is_covered"] is None]
    questions = _questions_to_employer(vacancy, flags, unknown)
    focus = _response_focus(vacancy, covered)
    risks = _quick_risks(vacancy, flags, missing)

    lines = [
        "",
        f"Карточка вакансии #{vacancy['id']}",
        f"Название: {vacancy['title']}",
        f"Компания: {_company_label(vacancy['company'])}",
        f"Формат: {_remote_label(vacancy['remote_format'])}",
        f"Зарплата: {_salary_label(vacancy)}",
        f"Направление: {ROLE_LABELS.get(vacancy['detected_role'], vacancy['detected_role'] or '-')}",
        f"Резюме: {vacancy['selected_resume'] or '-'}",
        f"Шанс: {_chance_label(vacancy['chance'])} ({vacancy['match_score'] if vacancy['match_score'] is not None else '-'}/100)",
        f"Решение: {_decision(vacancy)}",
        f"Почему: {_quick_reason(vacancy, flags, covered, missing, unknown, profile)}",
    ]

    if focus:
        lines.append(f"Что подчеркнуть: {focus}")
    if risks:
        lines.append(f"Риски: {risks}")
    if questions:
        lines.append(f"Вопрос работодателю: {questions[0]}")

    lines.extend(
        [
            "Команды дальше:",
            f"  draft {vacancy['id']}   создать черновик отклика",
            f"  explain {vacancy['id']} подробный разбор",
            f"  status {vacancy['id']} skipped   пропустить вакансию",
        ]
    )
    return "\n".join(lines)


def _why_role(vacancy: sqlite3.Row, covered: list[sqlite3.Row]) -> str:
    if covered:
        evidence = ", ".join((row["evidence"] or row["text"]) for row in covered[:5])
        return f"- Выбрано по совпадениям в требованиях: {evidence}."
    if vacancy["detected_role"] != "unknown":
        return f"- Роль похожа на {ROLE_LABELS.get(vacancy['detected_role'], vacancy['detected_role'])} по названию и ключевым словам."
    return "- Роль пока определена слабо: мало распознанных совпадений."


def _why_chance(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    missing: list[sqlite3.Row],
    unknown: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    high_flags = [row["text"] for row in flags if row["severity"] == "high"]
    medium_flags = [row["text"] for row in flags if row["severity"] == "medium"]

    if high_flags:
        return f"- Есть сильные стоп-факторы: {'; '.join(high_flags)}"
    if medium_flags:
        return f"- Есть ограничения: {'; '.join(medium_flags)}"
    if missing:
        return f"- Есть явные пробелы по требованиям: {len(missing)}."
    if unknown:
        return f"- В целом подходит, но {len(unknown)} требований надо проверить вручную. Английский в профиле: {profile.english_level}, разговорный: {profile.english_speaking}."
    return "- Критичных флагов нет, требования в основном совпадают с профилем."


def _questions_to_employer(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    unknown: list[sqlite3.Row],
) -> list[str]:
    questions: list[str] = []
    if vacancy["salary_min"] is None and vacancy["salary_max"] is None:
        questions.append("Какая зарплатная вилка и формат оплаты?")
    if vacancy["remote_format"] == "unknown":
        questions.append("Формат точно удалённый или есть офисные требования?")
    if any(row["flag_type"] == "experience" for row in flags):
        questions.append("Насколько критичен указанный опыт по годам, если есть релевантная практика?")
    if any(row["flag_type"] == "language" for row in flags):
        questions.append("Нужен разговорный английский или достаточно письменной переписки?")
    for row in unknown[:2]:
        questions.append(f"Насколько критично требование: {row['text']}")
    return questions


def _advice(vacancy: sqlite3.Row, flags: list[sqlite3.Row]) -> str:
    if vacancy["chance"] == "skip":
        return "лучше пропустить или уточнить условия до отклика."
    if vacancy["chance"] == "low":
        return "откликаться можно только если вакансия очень интересна; сначала уточнить флаги."
    if vacancy["chance"] == "medium":
        return "можно откликаться, но честно обозначить ограничения."
    return "стоит откликаться."


def _decision(vacancy: sqlite3.Row) -> str:
    chance = vacancy["chance"]
    if chance == "high":
        return "откликаться"
    if chance == "medium":
        return "откликаться, но аккуратно закрыть слабые места"
    if chance == "low":
        return "откликаться только если вакансия очень интересна"
    if chance == "skip":
        return "скорее пропустить или сначала уточнить условия"
    return "нужно больше данных"


def _quick_reason(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    covered: list[sqlite3.Row],
    missing: list[sqlite3.Row],
    unknown: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    high_flags = [row["text"] for row in flags if row["severity"] == "high"]
    medium_flags = [row["text"] for row in flags if row["severity"] == "medium"]
    if high_flags:
        return high_flags[0]
    if covered and not missing:
        return f"есть совпадения по требованиям ({len(covered)}), критичных пробелов не видно."
    if covered and missing:
        return f"есть совпадения ({len(covered)}), но есть явные пробелы ({len(missing)})."
    if medium_flags:
        return medium_flags[0]
    if unknown:
        return f"часть требований надо проверить вручную ({len(unknown)}); английский в профиле: {profile.english_level}."
    if vacancy["detected_role"] and vacancy["detected_role"] != "unknown":
        return "роль похожа на одно из целевых направлений."
    return "мало распознанных совпадений с профилем."


def _response_focus(vacancy: sqlite3.Row, covered: list[sqlite3.Row]) -> str:
    evidence: list[str] = []
    for row in covered:
        for value in _split_evidence(row["evidence"] or row["text"]):
            if value == "git" and "digital" in (row["text"] or "").lower():
                continue
            if value and value not in evidence:
                evidence.append(value)
    if evidence:
        return ", ".join(evidence[:4])

    role = vacancy["detected_role"]
    if role == "ai_automation":
        return "Python, автоматизацию, API, LLM-инструменты и быстрые прототипы"
    if role == "outreach":
        return "аутрич, переговоры, поиск площадок и работу с SEO-командой"
    if role == "link_builder":
        return "линкбилдинг, анализ доноров, SEO-инструменты и качество ссылок"
    if role == "ai_rater":
        return "внимательность к качеству данных, работу с инструкциями и языком"
    return ""


def _quick_risks(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    missing: list[sqlite3.Row],
) -> str:
    risks = [row["text"] for row in flags if row["severity"] in {"high", "medium"}]
    risks.extend(row["text"] for row in missing[:2])
    if vacancy["salary_min"] is None and vacancy["salary_max"] is None:
        risks.append("зарплата не указана")
    return "; ".join(risks[:3])


def _next_step(vacancy: sqlite3.Row) -> str:
    if vacancy["chance"] == "skip":
        return "не тратить время на черновик, сначала уточнить спорный пункт."
    if vacancy["chance"] == "low":
        return "открыть explain и решить, стоит ли делать короткий отклик."
    return "создать или проверить черновик отклика."


def _remote_label(value: str | None) -> str:
    return {
        "remote": "удалённо",
        "hybrid": "гибрид",
        "office": "офис",
        "relocation": "релокация",
        "unknown": "неясно",
        None: "-",
    }.get(value, value or "-")


def _chance_label(value: str | None) -> str:
    return {
        "high": "высокий",
        "medium": "средний",
        "low": "низкий",
        "skip": "лучше пропустить",
        "unknown": "неясно",
        None: "-",
    }.get(value, value or "-")


def _salary_label(vacancy: sqlite3.Row) -> str:
    salary_min = vacancy["salary_min"]
    salary_max = vacancy["salary_max"]
    currency = vacancy["salary_currency"] or ""
    if salary_min is None and salary_max is None:
        return "-"
    if salary_min is not None and salary_max is not None:
        return f"{salary_min}-{salary_max} {currency}".strip()
    if salary_min is not None:
        return f"от {salary_min} {currency}".strip()
    return f"до {salary_max} {currency}".strip()


def _company_label(value: str | None) -> str:
    if not value:
        return "-"
    lowered = value.lower().replace("ё", "е")
    looks_like_salary = bool(
        re.search(r"(\d[\d\s]{2,}|₽|\$|€|\bруб\b|\brub\b|\busd\b|\beur\b)", lowered)
        and any(marker in lowered for marker in ("до", "от", "зарплат", "доход", "salary", "руб", "rub", "usd", "₽", "$", "€"))
    )
    if looks_like_salary:
        return "-"
    return value


def _split_evidence(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]

