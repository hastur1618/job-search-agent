from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from job_agent.database import (
    DEFAULT_DB_PATH,
    add_contact_event,
    add_application,
    add_vacancy,
    approve_application,
    cleanup_empty_references,
    delete_application,
    delete_vacancy,
    get_application,
    get_vacancy,
    get_vacancy_flags,
    get_vacancy_requirements,
    list_contact_events,
    list_applications,
    list_due_followups,
    list_unsent_applications,
    list_vacancies,
    list_vacancies_without_applications,
    mark_application_sent,
    save_vacancy_analysis,
    update_application_draft_text,
    update_application_final_text,
    update_application_status,
    update_vacancy_status,
)
from job_agent.application_check import check_application_text, format_application_check
from job_agent.clipboard import ClipboardError, read_clipboard_text
from job_agent.draft import build_cover_letter_draft, build_service_summary
from job_agent.explain import build_explanation, build_quick_review, build_vacancy_card
from job_agent.profile import load_profile
from job_agent.today import TodaySummary, format_today_summary
from job_agent.vacancy_analysis import analyze_vacancy_text
from job_agent.vacancy_import import import_vacancy_text


STATUS_LABELS = {
    "new": "новая",
    "analyzed": "проанализирована",
    "drafted": "черновик создан",
    "applied": "отклик отправлен",
    "waiting": "ожидание",
    "ignored": "неактуально",
    "hr_interview": "HR-интервью",
    "technical_interview": "техническое интервью",
    "offer": "оффер",
    "rejected": "отказ",
    "closed": "закрыта",
    "skipped": "пропущена",
    "draft": "черновик",
    "sent": "отправлен",
    "followed_up": "follow-up отправлен",
    "interview": "интервью",
}

CHANCE_LABELS = {
    "high": "высокие",
    "medium": "средние",
    "low": "низкие",
    None: "-",
}

REMOTE_LABELS = {
    "unknown": "неясно",
    "remote": "удалённо",
    "hybrid": "гибрид",
    "office": "офис",
    "relocation": "релокация",
}

CHANNEL_LABELS = {
    "hh": "HH.ru",
    "telegram": "Telegram",
    "email": "Email",
    "linkedin": "LinkedIn",
    "form": "форма на сайте",
    "freelance": "фриланс-биржа",
    "manual": "вручную / другое",
    "other": "другое",
}

CHANNEL_CHOICES = [
    ("hh", "HH.ru"),
    ("telegram", "Telegram"),
    ("email", "Email"),
    ("linkedin", "LinkedIn"),
    ("form", "форма на сайте"),
    ("freelance", "фриланс-биржа"),
    ("manual", "вручную / другое"),
]

EVENT_LABELS = {
    "application": "отклик",
    "followup": "follow-up",
    "reply": "ответ",
    "interview": "интервью",
    "rejection": "отказ",
    "offer": "оффер",
    "note": "заметка",
}

DIRECTION_LABELS = {
    "outbound": "исходящее",
    "inbound": "входящее",
    "internal": "внутренняя запись",
}


def run_interactive(db_path: Path = DEFAULT_DB_PATH) -> None:
    print("Агент поиска работы")
    print("Выберите пункт меню или введите команду. 0 = выход, menu = показать меню.")
    _print_menu()
    last_vacancy_id: int | None = None
    last_application_id: int | None = None

    while True:
        try:
            command = input("агент> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return

        if not command:
            continue

        parts = command.split()
        name = _normalize_menu_choice(parts[0].lower())
        args = parts[1:]

        try:
            if name in {"quit", "exit", "q"}:
                return
            if name in {"menu", "m", "м"}:
                _print_menu()
            elif name in {"help", "h", "?"}:
                _print_help()
            elif name in {"workflow", "flow", "quick", "clip-flow"}:
                result = _workflow(db_path, use_clipboard=True)
                if result[0] is not None:
                    last_vacancy_id = result[0]
                if result[1] is not None:
                    last_application_id = result[1]
            elif name in {"workflow-paste", "flow-paste"}:
                result = _workflow(db_path, use_clipboard=False)
                if result[0] is not None:
                    last_vacancy_id = result[0]
                if result[1] is not None:
                    last_application_id = result[1]
            elif name in {"clip", "clipboard", "clip-vacancy"}:
                last_vacancy_id = _clip_vacancy(db_path)
            elif name == "paste":
                last_vacancy_id = _paste_vacancy(db_path)
            elif name in {"list", "list-vacancies"}:
                _list_vacancies(db_path)
            elif name in {"show", "show-vacancy"}:
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                _show_vacancy(vacancy_id, db_path)
            elif name in {"analyze", "analyze-vacancy"}:
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                _analyze_vacancy(vacancy_id, db_path)
            elif name == "explain":
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                _explain_vacancy(vacancy_id, db_path)
            elif name in {"apply", "create-application"}:
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                last_application_id = _create_application(vacancy_id, db_path)
            elif name in {"draft", "draft-vacancy"}:
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                last_application_id = _draft_application(vacancy_id, db_path)
            elif name in {"redraft", "redraft-application"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                if _redraft_application(application_id, db_path):
                    last_application_id = application_id
            elif name in {"apps", "list-applications"}:
                _list_applications(db_path)
            elif name in {"app", "show-application"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _show_application(application_id, db_path)
            elif name in {"history", "events"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _show_history(application_id, db_path)
            elif name in {"note", "add-note"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                text = " ".join(args[1:]).strip() if args else ""
                _add_note(application_id, text, db_path)
            elif name in {"event", "add-event"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _add_event(application_id, args[1:], db_path)
            elif name in {"check", "check-application"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _check_application(application_id, db_path)
            elif name == "approve":
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _approve_application(application_id, db_path)
            elif name in {"send", "sent"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _send_application(application_id, db_path)
            elif name in {"edit", "export-draft"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _export_draft(application_id, db_path)
            elif name == "open-edit":
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _open_edit(application_id, db_path)
            elif name in {"import-final", "load-edit"}:
                application_id = _id_or_last_or_prompt(args, last_application_id, "ID отклика")
                _import_final(application_id, db_path)
            elif name in {"followups", "due-followups"}:
                cutoff = args[0] if args else date.today().isoformat()
                _due_followups(cutoff, db_path)
            elif name in {"today", "next", "сегодня"}:
                cutoff = args[0] if args else date.today().isoformat()
                _today(cutoff, db_path)
            elif name in {"do", "next-action", "делай"}:
                cutoff = args[0] if args else date.today().isoformat()
                _do_next_action(cutoff, db_path)
            elif name in {"status", "update-status"}:
                _require_args(args, "status <vacancy_id> <status>")
                _update_vacancy_status(int(args[0]), args[1], db_path)
            elif name in {"app-status", "update-application-status"}:
                _require_args(args, "app-status <application_id> <status>")
                _update_application_status(int(args[0]), args[1], db_path)
            elif name in {"delete-app", "delete-application"}:
                _require_args(args, "delete-app <application_id>")
                _delete_application(int(args[0]), db_path)
            elif name in {"delete", "delete-vacancy"}:
                vacancy_id = _id_or_last_or_prompt(args, last_vacancy_id, "ID вакансии")
                _delete_vacancy(vacancy_id, db_path)
                if last_vacancy_id == vacancy_id:
                    last_vacancy_id = None
            elif name == "reset-broken":
                _reset_broken(db_path)
            else:
                print("Неизвестная команда. Введите help или menu.")
        except ValueError as error:
            print(f"Ошибка: {error}")


def _print_menu() -> None:
    print(
        """
Меню:
  1  Быстрый сценарий из буфера: вакансия -> черновик -> проверка -> отправка
  2  Добавить вакансию из буфера обмена
  3  Вставить вакансию вручную
  4  Показать вакансии
  5  Показать отклики
  6  Открыть карточку вакансии
  7  Открыть карточку отклика
  8  Объяснить анализ вакансии
  9  Создать черновик отклика
  10 Пересоздать черновик отклика
  11 Открыть черновик в редакторе
  12 Импортировать отредактированный текст
  13 Проверить отклик перед отправкой
  14 Одобрить отклик
  15 Отметить как отправленный
  16 Показать follow-up
  17 Сегодня / что делать дальше
  18 Выполнить рекомендуемый шаг
  19 Показать историю отклика
  20 Добавить заметку к отклику
  21 Показать команды
  0  Выход
""".strip()
    )


def _normalize_menu_choice(value: str) -> str:
    choices = {
        "0": "quit",
        "1": "workflow",
        "2": "clip",
        "3": "paste",
        "4": "list",
        "5": "apps",
        "6": "show",
        "7": "app",
        "8": "explain",
        "9": "draft",
        "10": "redraft",
        "11": "open-edit",
        "12": "import-final",
        "13": "check",
        "14": "approve",
        "15": "send",
        "16": "followups",
        "17": "today",
        "18": "do",
        "19": "history",
        "20": "note",
        "21": "help",
    }
    return choices.get(value, value)


def _print_help() -> None:
    print(
        """
Команды:
  workflow               Быстрый сценарий из буфера обмена
  clip                   Взять текст вакансии из буфера, сохранить и проанализировать
  workflow-paste         Полный сценарий с ручной вставкой текста
  paste                  Вставить текст вакансии вручную, сохранить и проанализировать
  list                   Показать вакансии
  show [id]              Показать карточку вакансии
  analyze [id]           Повторить локальный анализ вакансии
  explain [id]           Объяснить выбор резюме, шансы, риски и вопросы
  draft [id]             Создать черновик отклика
  redraft [id]           Пересоздать черновик существующего отклика
  apply [id]             Создать запись отклика вручную
  apps                   Показать отклики
  app <id>               Показать карточку отклика
  history [id]           Показать историю контактов по отклику
  note [id] [текст]      Добавить заметку в историю отклика
  event [id]             Добавить событие: ответ, интервью, отказ, оффер
  check [id]             Проверить отклик перед отправкой
  edit [id]              Экспортировать черновик в data/drafts/application_ID.txt
  open-edit [id]         Открыть черновик в редакторе
  import-final [id]      Импортировать отредактированный текст
  approve [id]           Одобрить отклик
  send [id]              Отметить отклик отправленным и поставить follow-up
  followups [YYYY-MM-DD] Показать follow-up на дату
  today [YYYY-MM-DD]     Показать сводку дел и следующий шаг
  do                     Выполнить рекомендуемый следующий шаг
  status <id> <status>   Обновить статус вакансии
  app-status <id> <status> Обновить статус отклика
  delete [id]            Удалить вакансию
  delete-app <id>        Удалить отклик
  reset-broken           Удалить вакансии с битой кодировкой
  quit                   Выйти

Для быстрого режима: сначала скопируйте текст вакансии, затем выберите пункт 1 или 2.
Для paste: вставьте текст вакансии, затем напишите /// на новой строке.
""".strip()
    )


def _workflow(db_path: Path, *, use_clipboard: bool) -> tuple[int | None, int | None]:
    if use_clipboard:
        print("Быстрый сценарий: читаю вакансию из буфера обмена.")
        vacancy_id = _clip_vacancy(db_path)
    else:
        print("Полный сценарий: вставьте текст вакансии. В конце напишите /// на новой строке.")
        vacancy_id = _paste_vacancy(db_path)
    application_id = _draft_application(vacancy_id, db_path)
    if application_id is None:
        return vacancy_id, None

    if _ask_yes_no("Открыть черновик для редактирования?", default=True):
        _open_edit(application_id, db_path)
        input("Сохраните файл, затем нажмите Enter здесь, чтобы импортировать текст...")
        _import_final(application_id, db_path)

    _check_application(application_id, db_path)
    if _ask_yes_no("Одобрить этот отклик?", default=True):
        _approve_application(application_id, db_path)

    if _ask_yes_no("Отметить отклик отправленным сейчас?", default=False):
        _send_application(application_id, db_path)
    else:
        print("Черновик сохранён. Отправку можно отметить позже командой send или пунктом 13.")

    return vacancy_id, application_id


def _clip_vacancy(db_path: Path) -> int:
    try:
        text = read_clipboard_text()
    except ClipboardError as error:
        raise ValueError(str(error)) from error
    print("Текст взят из буфера обмена.")
    return _save_vacancy_text(text, db_path)


def _paste_vacancy(db_path: Path) -> int:
    print("Вставьте текст вакансии. В конце напишите /// на новой строке.")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "///":
            break
        lines.append(line)

    return _save_vacancy_text("\n".join(lines), db_path)


def _save_vacancy_text(text: str, db_path: Path) -> int:
    imported = import_vacancy_text(text)
    vacancy_id = add_vacancy(
        title=imported.title,
        company=imported.company,
        source_name=imported.source_name,
        source_type=imported.source_type,
        source_url=imported.source_url,
        raw_text=imported.raw_text,
        language=imported.language,
        remote_format=imported.remote_format,
        salary_min=imported.salary_min,
        salary_max=imported.salary_max,
        salary_currency=imported.salary_currency,
        db_path=db_path,
    )
    _analyze_vacancy(vacancy_id, db_path, quiet=True)
    row = get_vacancy(vacancy_id, db_path=db_path)
    print(f"Сохранено #{vacancy_id}: {row['title']}")
    print(
        f"Роль={_value(row['detected_role'])} "
        f"Резюме={_value(row['selected_resume'])} "
        f"Шанс={_chance_label(row['chance'])} "
        f"Балл={row['match_score']}"
    )
    _show_vacancy_card(vacancy_id, db_path)
    return vacancy_id


def _list_vacancies(db_path: Path) -> None:
    rows = list_vacancies(limit=50, db_path=db_path)
    if not rows:
        print("Вакансий пока нет.")
        return
    for row in rows:
        print(
            f"#{row['id']} | {_status_label(row['status'])} | {row['title']} | "
            f"{row['company'] or '-'} | шанс: {_chance_label(row['chance'])}"
        )


def _show_vacancy(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return
    if row["status"] == "new" or row["match_score"] is None:
        _analyze_vacancy(vacancy_id, db_path, quiet=True)
        row = get_vacancy(vacancy_id, db_path=db_path)
    _show_vacancy_card(vacancy_id, db_path)
    print(f"URL: {row['source_url'] or '-'}")
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    if flags:
        print("Флаги:")
        for flag in flags:
            print(f"- [{flag['severity']}] {flag['text']}")
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    if requirements:
        print("Требования:")
        for requirement in requirements:
            covered = {1: "да", 0: "нет", None: "неясно"}[requirement["is_covered"]]
            evidence = f" ({requirement['evidence']})" if requirement["evidence"] else ""
            print(f"- [{covered}] {requirement['text']}{evidence}")


def _analyze_vacancy(vacancy_id: int, db_path: Path, *, quiet: bool = False) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return
    analysis = analyze_vacancy_text(
        title=row["title"],
        raw_text=row["raw_text"],
        remote_format=row["remote_format"],
        salary_min=row["salary_min"],
        salary_currency=row["salary_currency"],
        experience_min_years=row["experience_min_years"],
    )
    save_vacancy_analysis(
        vacancy_id=vacancy_id,
        detected_role=analysis.detected_role,
        selected_resume=analysis.selected_resume,
        match_score=analysis.match_score,
        chance=analysis.chance,
        requirements=analysis.requirements,
        flags=analysis.flags,
        db_path=db_path,
    )
    if not quiet:
        print(
            f"Проанализировано #{vacancy_id}: "
            f"{analysis.detected_role}, шанс: {_chance_label(analysis.chance)}, балл={analysis.match_score}"
        )


def _explain_vacancy(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return
    if row["status"] == "new" or row["match_score"] is None:
        _analyze_vacancy(vacancy_id, db_path, quiet=True)
        row = get_vacancy(vacancy_id, db_path=db_path)
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    print(build_explanation(row, flags, requirements, load_profile()))


def _show_quick_review(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        return
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    print(build_quick_review(row, flags, requirements, load_profile()))


def _show_vacancy_card(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        return
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    print(build_vacancy_card(row, flags, requirements, load_profile()))


def _create_application(vacancy_id: int, db_path: Path) -> int | None:
    applied_at = input(f"Дата отправки [{date.today().isoformat()}]: ").strip() or date.today().isoformat()
    next_followup_at = input("Дата follow-up [пусто = пропустить]: ").strip() or None
    channel = _ask_channel("Куда отправили отклик?", default="manual")
    application_id = add_application(
        vacancy_id=vacancy_id,
        channel=channel,
        applied_at=applied_at,
        next_followup_at=next_followup_at,
        db_path=db_path,
    )
    if application_id is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return None
    else:
        print(f"Отклик создан: #{application_id}")
        return application_id


def _draft_application(vacancy_id: int, db_path: Path) -> int | None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return None

    draft_data = _build_draft_for_vacancy(vacancy_id, db_path)
    if draft_data is None:
        return None
    summary, draft = draft_data
    application_id = add_application(
        vacancy_id=vacancy_id,
        channel="manual",
        generated_text=draft,
        db_path=db_path,
    )
    print(f"Черновик создан: отклик #{application_id}")
    print("")
    print(summary)
    print("")
    print(draft)
    return application_id


def _redraft_application(application_id: int, db_path: Path) -> bool:
    application = get_application(application_id, db_path=db_path)
    if application is None:
        print(f"Отклик не найден: #{application_id}")
        return False

    draft_data = _build_draft_for_vacancy(application["vacancy_id"], db_path)
    if draft_data is None:
        return False
    summary, draft = draft_data
    updated = update_application_draft_text(application_id, draft, db_path=db_path)
    if not updated:
        print(f"Отклик не найден: #{application_id}")
        return False

    print(f"Черновик пересоздан: отклик #{application_id}")
    print("Финальный текст и одобрение сброшены, отклик нужно проверить заново.")
    print("")
    print(summary)
    print("")
    print(draft)
    return True


def _build_draft_for_vacancy(vacancy_id: int, db_path: Path) -> tuple[str, str] | None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        print(f"Вакансия не найдена: #{vacancy_id}")
        return None
    if row["status"] == "new" or row["match_score"] is None:
        _analyze_vacancy(vacancy_id, db_path, quiet=True)
        row = get_vacancy(vacancy_id, db_path=db_path)

    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    profile = load_profile()
    summary = build_service_summary(row, flags, requirements, profile)
    draft = build_cover_letter_draft(row, flags, requirements, profile)
    return summary, draft


def _list_applications(db_path: Path) -> None:
    rows = list_applications(limit=50, db_path=db_path)
    if not rows:
        print("Откликов пока нет.")
        return
    for row in rows:
        print(
            f"#{row['id']} | {_status_label(row['status'])} | "
            f"{row['vacancy_title']} | канал: {_channel_label(row['channel'])} | "
            f"follow-up={row['next_followup_at'] or '-'}"
        )


def _show_application(application_id: int, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    print(f"#{row['id']} {row['vacancy_title']}")
    print(f"Компания: {row['company'] or '-'}")
    print(f"Статус: {_status_label(row['status'])} Канал: {_channel_label(row['channel'])}")
    print(f"Отправлено: {row['applied_at'] or '-'} Следующий follow-up: {row['next_followup_at'] or '-'}")
    print(f"Одобрено: {'да' if row['user_approved'] else 'нет'}")
    if row["final_text"] or row["generated_text"]:
        print("")
        print(row["final_text"] or row["generated_text"])
    events = list_contact_events(application_id=application_id, limit=3, db_path=db_path)
    if events:
        print("")
        print("Последние события:")
        for event in events:
            print(_format_event(event))


def _check_application(application_id: int, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    print(format_application_check(check_application_text(row)))


def _draft_path(application_id: int) -> Path:
    return DEFAULT_DB_PATH.parents[1] / "data" / "drafts" / f"application_{application_id}.txt"


def _export_draft(application_id: int, db_path: Path) -> Path | None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return None
    text = row["final_text"] or row["generated_text"]
    if not text:
        print("У отклика нет текста черновика.")
        return None
    path = _draft_path(application_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Черновик экспортирован: {path}")
    print("Отредактируйте файл, сохраните его, затем запустите import-final или пункт 10.")
    return path


def _open_edit(application_id: int, db_path: Path) -> None:
    path = _export_draft(application_id, db_path)
    if path is None:
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        print("Открыто в редакторе по умолчанию. Сохраните файл, затем запустите import-final или пункт 10.")
    except OSError as error:
        print(f"Не удалось открыть редактор: {error}")
        print(f"Откройте файл вручную: {path}")


def _import_final(application_id: int, db_path: Path) -> None:
    path = _draft_path(application_id)
    if not path.exists():
        print(f"Файл черновика не найден: {path}")
        return
    final_text = path.read_text(encoding="utf-8").strip()
    if not final_text:
        print("Файл черновика пустой. Импорт отменён.")
        return
    updated = update_application_final_text(application_id, final_text, db_path=db_path)
    print("Финальный текст импортирован." if updated else "Отклик не найден.")


def _due_followups(cutoff: str, db_path: Path) -> None:
    rows = list_due_followups(due_date=cutoff, db_path=db_path)
    if not rows:
        print("Нет follow-up на выбранную дату.")
        return
    for row in rows:
        print(f"#{row['id']} | due={row['next_followup_at']} | {row['vacancy_title']} | {row['company'] or '-'}")


def _show_history(application_id: int, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    events = list_contact_events(application_id=application_id, limit=50, db_path=db_path)
    if not events:
        print("История пока пустая.")
        return
    print(f"История отклика #{application_id}: {row['vacancy_title']}")
    for event in events:
        print(_format_event(event))


def _add_note(application_id: int, text: str, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    if not text:
        text = input("Текст заметки: ").strip()
    if not text:
        print("Заметка пустая. Ничего не сохранено.")
        return
    event_id = add_contact_event(
        application_id=application_id,
        event_type="note",
        direction="internal",
        text=text,
        db_path=db_path,
    )
    print(f"Заметка добавлена: событие #{event_id}" if event_id else "Отклик не найден.")


def _add_event(application_id: int, args: list[str], db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    event_type = args[0].strip().lower() if args else _ask_event_type()
    event_type = _normalize_event_type(event_type)
    text = " ".join(args[1:]).strip() if len(args) > 1 else input("Текст события: ").strip()
    direction = "inbound" if event_type in {"reply", "interview", "rejection", "offer"} else "internal"
    event_id = add_contact_event(
        application_id=application_id,
        event_type=event_type,
        direction=direction,
        text=text or None,
        db_path=db_path,
    )
    next_status = _status_for_event(event_type)
    if event_id and next_status:
        update_application_status(application_id, next_status, db_path=db_path)
    print(f"Событие добавлено: #{event_id}" if event_id else "Отклик не найден.")


def _ask_event_type() -> str:
    print("Тип события:")
    choices = [
        ("reply", "ответ работодателя"),
        ("interview", "интервью"),
        ("rejection", "отказ"),
        ("offer", "оффер"),
        ("followup", "follow-up"),
        ("note", "заметка"),
    ]
    for index, (_, label) in enumerate(choices, start=1):
        print(f"  {index}  {label}")
    answer = input("Выбор: ").strip().lower()
    if answer.isdigit():
        index = int(answer)
        if 1 <= index <= len(choices):
            return choices[index - 1][0]
    return answer


def _normalize_event_type(value: str) -> str:
    mapping = {
        "1": "reply",
        "2": "interview",
        "3": "rejection",
        "4": "offer",
        "5": "followup",
        "6": "note",
        "ответ": "reply",
        "reply": "reply",
        "интервью": "interview",
        "interview": "interview",
        "отказ": "rejection",
        "rejection": "rejection",
        "offer": "offer",
        "оффер": "offer",
        "followup": "followup",
        "follow-up": "followup",
        "заметка": "note",
        "note": "note",
    }
    normalized = mapping.get(value)
    if not normalized:
        raise ValueError("Неизвестный тип события.")
    return normalized


def _status_for_event(event_type: str) -> str | None:
    return {
        "followup": "followed_up",
        "interview": "interview",
        "rejection": "rejected",
        "offer": "offer",
    }.get(event_type)


def _today(cutoff: str, db_path: Path) -> None:
    summary = TodaySummary(
        due_followups=list_due_followups(due_date=cutoff, db_path=db_path),
        unsent_applications=list_unsent_applications(limit=20, db_path=db_path),
        vacancies_without_applications=list_vacancies_without_applications(limit=20, db_path=db_path),
    )
    print(format_today_summary(summary, today=cutoff))


def _do_next_action(cutoff: str, db_path: Path) -> None:
    due_followups = list_due_followups(due_date=cutoff, db_path=db_path)
    if due_followups:
        row = due_followups[0]
        print(f"Следующий шаг: follow-up по отклику #{row['id']}.")
        print(f"Вакансия: {row['vacancy_title']} | {row['company'] or '-'}")
        print(f"Срок follow-up: {row['next_followup_at']}")
        if _ask_yes_no("Отметить follow-up выполненным?", default=False):
            _update_application_status(row["id"], "followed_up", db_path)
            add_contact_event(
                application_id=row["id"],
                event_type="followup",
                direction="outbound",
                text="Follow-up отправлен.",
                event_at=cutoff,
                db_path=db_path,
            )
        return

    unsent = list_unsent_applications(limit=20, db_path=db_path)
    if unsent:
        row = unsent[0]
        application_id = row["id"]
        if not row["generated_text"] and not row["final_text"]:
            print(f"Следующий шаг: пересоздать черновик отклика #{application_id}.")
            _redraft_application(application_id, db_path)
            return

        if not row["user_approved"]:
            print(f"Следующий шаг: проверить и одобрить отклик #{application_id}.")
            _check_application(application_id, db_path)
            if _ask_yes_no("Одобрить этот отклик сейчас?", default=True):
                _approve_application(application_id, db_path)
            else:
                print("Отклик не одобрен. Можно вернуться к нему позже через пункт 17.")
            return

        print(f"Следующий шаг: отметить отклик #{application_id} отправленным.")
        if _ask_yes_no("Отметить отправку сейчас?", default=True):
            _send_application(application_id, db_path)
        else:
            print("Отправка не отмечена. Можно вернуться к ней позже через пункт 17.")
        return

    vacancies = list_vacancies_without_applications(limit=20, db_path=db_path)
    if vacancies:
        row = vacancies[0]
        print(f"Следующий шаг: создать черновик для вакансии #{row['id']}.")
        _draft_application(row["id"], db_path)
        return

    print("Сейчас нет активных действий. Добавьте новую вакансию через пункт 2 или команду paste.")


def _approve_application(application_id: int, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    check = check_application_text(row)
    if not check.can_send:
        print(format_application_check(check))
        answer = input("Есть предупреждения. Всё равно одобрить? [y/N]: ").strip().lower()
        if answer not in {"y", "yes", "д", "да"}:
            print("Не одобрено.")
            return
    print("Одобрено." if approve_application(application_id, db_path=db_path) else "Отклик не найден.")


def _send_application(application_id: int, db_path: Path) -> None:
    row = get_application(application_id, db_path=db_path)
    if row is None:
        print(f"Отклик не найден: #{application_id}")
        return
    if not row["user_approved"]:
        answer = input("Отклик не одобрен. Всё равно одобрить и отметить отправленным? [y/N]: ").strip().lower()
        if answer not in {"y", "yes", "д", "да"}:
            print("Отменено.")
            return
        approve_application(application_id, db_path=db_path)

    today = date.today().isoformat()
    default_followup = (date.today() + timedelta(days=7)).isoformat()
    applied_at = input(f"Дата отправки [{today}]: ").strip() or today
    next_followup_at = input(f"Дата follow-up [{default_followup}, пусто = оставить дату по умолчанию]: ").strip()
    if not next_followup_at:
        next_followup_at = default_followup
    channel = _ask_channel("Куда отправили отклик?", default=row["channel"] or "manual")

    sent = mark_application_sent(
        application_id=application_id,
        channel=channel,
        applied_at=applied_at,
        next_followup_at=next_followup_at,
        db_path=db_path,
    )
    if sent:
        add_contact_event(
            application_id=application_id,
            event_type="application",
            direction="outbound",
            text="Отклик отправлен.",
            event_at=applied_at,
            db_path=db_path,
        )
    print("Отмечено как отправленное." if sent else "Отклик не найден.")


def _update_vacancy_status(vacancy_id: int, status: str, db_path: Path) -> None:
    print("Обновлено." if update_vacancy_status(vacancy_id, status, db_path=db_path) else "Вакансия не найдена.")


def _update_application_status(application_id: int, status: str, db_path: Path) -> None:
    print("Обновлено." if update_application_status(application_id, status, db_path=db_path) else "Отклик не найден.")


def _delete_application(application_id: int, db_path: Path) -> None:
    print("Удалено." if delete_application(application_id, db_path=db_path) else "Отклик не найден.")


def _delete_vacancy(vacancy_id: int, db_path: Path) -> None:
    print("Удалено." if delete_vacancy(vacancy_id, db_path=db_path) else "Вакансия не найдена.")


def _reset_broken(db_path: Path) -> None:
    rows = list_vacancies(limit=200, db_path=db_path)
    deleted = 0
    for row in rows:
        vacancy = get_vacancy(row["id"], db_path=db_path)
        raw_text = vacancy["raw_text"] or ""
        if _looks_broken(raw_text):
            if delete_vacancy(row["id"], db_path=db_path):
                deleted += 1
    cleanup_empty_references(db_path=db_path)
    print(f"Удалено вакансий с битой кодировкой: {deleted}")


def _looks_broken(raw_text: str) -> bool:
    if len(raw_text) < 300:
        return False

    cyrillic = sum(1 for char in raw_text if "а" <= char.lower() <= "я" or char.lower() == "ё")
    latin = sum(1 for char in raw_text if "a" <= char.lower() <= "z")
    stripped_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    colon_fragments = sum(1 for line in stripped_lines if line.startswith(":") or line.endswith(":"))
    very_short_lines = sum(1 for line in stripped_lines if len(line) <= 3)

    return (
        cyrillic < 20
        and latin > 20
        and (colon_fragments >= 4 or very_short_lines >= 4)
    )


def _require_args(args: list[str], usage: str) -> None:
    if not args:
        raise ValueError(f"Формат: {usage}")


def _id_or_last(args: list[str], last_id: int | None, usage: str) -> int:
    if args:
        return int(args[0])
    if last_id is not None:
        return last_id
    raise ValueError(f"Формат: {usage}")


def _id_or_last_or_prompt(args: list[str], last_id: int | None, label: str) -> int:
    if args:
        return int(args[0])
    if last_id is not None:
        return last_id
    value = input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} обязателен.")
    return int(value)


def _ask_yes_no(prompt: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "д", "да"}


def _ask_channel(prompt: str, *, default: str = "manual") -> str:
    default_label = _channel_label(default)
    print(prompt)
    for index, (_, label) in enumerate(CHANNEL_CHOICES, start=1):
        default_marker = " [по умолчанию]" if label == default_label else ""
        print(f"  {index}  {label}{default_marker}")
    answer = input(f"Выбор [{default_label}]: ").strip().lower()
    if not answer:
        return default
    if answer.isdigit():
        index = int(answer)
        if 1 <= index <= len(CHANNEL_CHOICES):
            return CHANNEL_CHOICES[index - 1][0]
        raise ValueError("Неверный номер канала.")

    normalized = {
        "нн": "hh",
        "hh": "hh",
        "hh.ru": "hh",
        "телеграм": "telegram",
        "telegram": "telegram",
        "tg": "telegram",
        "почта": "email",
        "email": "email",
        "mail": "email",
        "linkedin": "linkedin",
        "линкедин": "linkedin",
        "форма": "form",
        "form": "form",
        "сайт": "form",
        "фриланс": "freelance",
        "freelance": "freelance",
        "manual": "manual",
        "вручную": "manual",
        "другое": "other",
        "other": "other",
    }.get(answer)
    if normalized:
        return normalized
    raise ValueError("Не понял канал. Введите номер из списка.")


def _status_label(value: str | None) -> str:
    return STATUS_LABELS.get(value, value or "-")


def _chance_label(value: str | None) -> str:
    return CHANCE_LABELS.get(value, value or "-")


def _remote_label(value: str | None) -> str:
    return REMOTE_LABELS.get(value, value or "-")


def _channel_label(value: str | None) -> str:
    return CHANNEL_LABELS.get(value, value or "-")


def _event_label(value: str | None) -> str:
    return EVENT_LABELS.get(value, value or "-")


def _direction_label(value: str | None) -> str:
    return DIRECTION_LABELS.get(value, value or "-")


def _format_event(event: object) -> str:
    text = event["text"] or event["notes"] or ""
    suffix = f" | {text}" if text else ""
    return (
        f"- #{event['id']} | {event['event_at']} | "
        f"{_event_label(event['event_type'])} | {_direction_label(event['direction'])}{suffix}"
    )


def _value(value: object) -> str:
    return str(value) if value not in {None, ""} else "-"

