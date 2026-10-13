from __future__ import annotations

import argparse
import os
import sys
from datetime import date
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
    get_db_info,
    get_vacancy,
    get_vacancy_flags,
    get_vacancy_requirements,
    init_db,
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
from job_agent.vacancy_analysis import analyze_vacancy_text
from job_agent.vacancy_import import import_vacancy_file, import_vacancy_text
from job_agent.interactive import run_interactive
from job_agent.profile import load_profile
from job_agent.today import TodaySummary, format_today_summary


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-agent",
        description="Local job search assistant database tools.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path. Default: {DEFAULT_DB_PATH}",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db", help="Create or update the local database schema.")
    subparsers.add_parser("db-info", help="Show database tables and row counts.")
    subparsers.add_parser("cleanup-empty", help="Remove companies and sources with no vacancies.")
    today_parser = subparsers.add_parser("today", help="Show today's job-search action summary.")
    today_parser.add_argument("--date", default=date.today().isoformat(), help="Date cutoff, default: today.")

    add_parser = subparsers.add_parser("add-vacancy", help="Add a vacancy to the local tracker.")
    add_parser.add_argument("--title", required=True, help="Vacancy title.")
    add_parser.add_argument("--company", help="Company name.")
    add_parser.add_argument("--source", default="manual", help="Source name, for example hh or LinkedIn.")
    add_parser.add_argument(
        "--source-type",
        default="manual",
        choices=["hh", "linkedin", "telegram", "remote_board", "freelance", "company_site", "manual", "other"],
        help="Source type.",
    )
    add_parser.add_argument("--url", help="Vacancy URL.")
    add_parser.add_argument("--text-file", type=Path, help="Path to a text file with the full vacancy text.")
    add_parser.add_argument(
        "--language",
        default="unknown",
        choices=["ru", "en", "mixed", "unknown"],
        help="Vacancy language.",
    )
    add_parser.add_argument(
        "--remote-format",
        default="unknown",
        choices=["unknown", "remote", "hybrid", "office", "relocation"],
        help="Work format.",
    )
    add_parser.add_argument("--salary-min", type=int, help="Minimum salary.")
    add_parser.add_argument("--salary-max", type=int, help="Maximum salary.")
    add_parser.add_argument("--salary-currency", help="Salary currency, for example RUB or USD.")

    import_parser = subparsers.add_parser("import-vacancy", help="Import a vacancy from a UTF-8 text file.")
    import_parser.add_argument("path", type=Path, help="Path to vacancy text file.")

    paste_parser = subparsers.add_parser("paste-vacancy", help="Paste vacancy text directly into the terminal.")
    paste_parser.add_argument("--title", default="Pasted vacancy", help="Fallback title if title cannot be detected.")
    paste_parser.add_argument("--source", help="Fallback source name, for example hh or telegram.")

    clip_parser = subparsers.add_parser("clip-vacancy", help="Import a vacancy from the clipboard.")
    clip_parser.add_argument("--title", default="Clipboard vacancy", help="Fallback title if title cannot be detected.")
    clip_parser.add_argument("--source", help="Fallback source name, for example hh or telegram.")

    paste_analyze_parser = subparsers.add_parser(
        "paste-analyze",
        help="Paste vacancy text, save it, and analyze it immediately.",
    )
    paste_analyze_parser.add_argument("--title", default="Pasted vacancy", help="Fallback title if title cannot be detected.")
    paste_analyze_parser.add_argument("--source", help="Fallback source name, for example hh or telegram.")

    clip_analyze_parser = subparsers.add_parser(
        "clip-analyze",
        help="Import a vacancy from the clipboard and analyze it immediately.",
    )
    clip_analyze_parser.add_argument("--title", default="Clipboard vacancy", help="Fallback title if title cannot be detected.")
    clip_analyze_parser.add_argument("--source", help="Fallback source name, for example hh or telegram.")

    list_parser = subparsers.add_parser("list-vacancies", help="List vacancies from the local tracker.")
    list_parser.add_argument("--status", help="Filter by vacancy status.")
    list_parser.add_argument("--limit", type=int, default=20, help="Maximum rows to show.")

    show_parser = subparsers.add_parser("show-vacancy", help="Show one vacancy by ID.")
    show_parser.add_argument("id", type=int, help="Vacancy ID.")

    analyze_parser = subparsers.add_parser("analyze-vacancy", help="Analyze one vacancy with local rules.")
    analyze_parser.add_argument("id", type=int, help="Vacancy ID.")

    explain_parser = subparsers.add_parser("explain-vacancy", help="Explain analysis result for one vacancy.")
    explain_parser.add_argument("id", type=int, help="Vacancy ID.")

    draft_parser = subparsers.add_parser("draft-vacancy", help="Create a local cover-letter draft for a vacancy.")
    draft_parser.add_argument("id", type=int, help="Vacancy ID.")

    redraft_parser = subparsers.add_parser("redraft-application", help="Regenerate a clean draft for an existing application.")
    redraft_parser.add_argument("id", type=int, help="Application ID.")

    status_parser = subparsers.add_parser("update-status", help="Update vacancy status.")
    status_parser.add_argument("id", type=int, help="Vacancy ID.")
    status_parser.add_argument(
        "status",
        choices=[
            "new",
            "analyzed",
            "drafted",
            "applied",
            "waiting",
            "ignored",
            "hr_interview",
            "technical_interview",
            "offer",
            "rejected",
            "closed",
            "skipped",
        ],
        help="New vacancy status.",
    )

    delete_parser = subparsers.add_parser("delete-vacancy", help="Delete one vacancy by ID.")
    delete_parser.add_argument("id", type=int, help="Vacancy ID.")

    application_parser = subparsers.add_parser("create-application", help="Create an application record for a vacancy.")
    application_parser.add_argument("vacancy_id", type=int, help="Vacancy ID.")
    application_parser.add_argument(
        "--channel",
        default="manual",
        choices=["hh", "email", "telegram", "linkedin", "form", "freelance", "manual", "other"],
        help="Application channel.",
    )
    application_parser.add_argument("--generated-text-file", type=Path, help="Path to generated draft text.")
    application_parser.add_argument("--final-text-file", type=Path, help="Path to final text sent or ready to send.")
    application_parser.add_argument("--approved", action="store_true", help="Mark final text as user-approved.")
    application_parser.add_argument("--applied-at", help="Date sent, for example 2026-10-13.")
    application_parser.add_argument("--next-followup-at", help="Follow-up date, for example 2026-10-20.")
    application_parser.add_argument("--notes", help="Free-form notes.")

    list_applications_parser = subparsers.add_parser("list-applications", help="List application records.")
    list_applications_parser.add_argument("--status", help="Filter by application status.")
    list_applications_parser.add_argument("--limit", type=int, default=20, help="Maximum rows to show.")

    show_application_parser = subparsers.add_parser("show-application", help="Show one application by ID.")
    show_application_parser.add_argument("id", type=int, help="Application ID.")

    history_parser = subparsers.add_parser("application-history", help="Show contact history for one application.")
    history_parser.add_argument("id", type=int, help="Application ID.")
    history_parser.add_argument("--limit", type=int, default=20, help="Maximum events to show.")

    note_parser = subparsers.add_parser("add-note", help="Add an internal note to one application.")
    note_parser.add_argument("id", type=int, help="Application ID.")
    note_parser.add_argument("text", help="Note text.")

    event_parser = subparsers.add_parser("add-event", help="Add a contact event to one application.")
    event_parser.add_argument("id", type=int, help="Application ID.")
    event_parser.add_argument(
        "event_type",
        choices=["reply", "interview", "rejection", "offer", "followup", "note"],
        help="Event type.",
    )
    event_parser.add_argument("text", help="Event text.")

    check_application_parser = subparsers.add_parser("check-application", help="Check whether an application text is ready to send.")
    check_application_parser.add_argument("id", type=int, help="Application ID.")

    app_status_parser = subparsers.add_parser("update-application-status", help="Update application status.")
    app_status_parser.add_argument("id", type=int, help="Application ID.")
    app_status_parser.add_argument(
        "status",
        choices=["draft", "sent", "waiting", "followed_up", "ignored", "interview", "offer", "rejected", "closed"],
        help="New application status.",
    )

    due_parser = subparsers.add_parser("due-followups", help="Show applications with due follow-ups.")
    due_parser.add_argument("--date", default=date.today().isoformat(), help="Due date cutoff, default: today.")

    approve_parser = subparsers.add_parser("approve-application", help="Mark an application draft as approved.")
    approve_parser.add_argument("id", type=int, help="Application ID.")

    sent_parser = subparsers.add_parser("mark-sent", help="Mark an application as manually sent.")
    sent_parser.add_argument("id", type=int, help="Application ID.")
    sent_parser.add_argument("--channel", default="manual", choices=["hh", "email", "telegram", "linkedin", "form", "freelance", "manual", "other"])
    sent_parser.add_argument("--applied-at", default=date.today().isoformat())
    sent_parser.add_argument("--next-followup-at")

    delete_app_parser = subparsers.add_parser("delete-application", help="Delete one application by ID.")
    delete_app_parser.add_argument("id", type=int, help="Application ID.")

    export_parser = subparsers.add_parser("export-draft", help="Export an application draft to data/drafts.")
    export_parser.add_argument("id", type=int, help="Application ID.")

    open_edit_parser = subparsers.add_parser("open-edit", help="Export a draft and open it in the default editor.")
    open_edit_parser.add_argument("id", type=int, help="Application ID.")

    import_final_parser = subparsers.add_parser("import-final", help="Import edited final text from data/drafts.")
    import_final_parser.add_argument("id", type=int, help="Application ID.")

    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        run_interactive(args.db)
        return

    if args.command == "init-db":
        init_db(args.db)
        print(f"Database ready: {args.db}")
        return

    if args.command == "db-info":
        info = get_db_info(args.db)
        print(f"Database: {args.db}")
        for table, count in info.items():
            print(f"{table}: {count}")
        return

    if args.command == "cleanup-empty":
        deleted = cleanup_empty_references(args.db)
        print(f"Deleted empty companies: {deleted['companies']}")
        print(f"Deleted empty sources: {deleted['sources']}")
        return

    if args.command == "today":
        summary = TodaySummary(
            due_followups=list_due_followups(due_date=args.date, db_path=args.db),
            unsent_applications=list_unsent_applications(limit=20, db_path=args.db),
            vacancies_without_applications=list_vacancies_without_applications(limit=20, db_path=args.db),
        )
        print(format_today_summary(summary, today=args.date))
        return

    if args.command == "add-vacancy":
        raw_text = None
        if args.text_file:
            raw_text = args.text_file.read_text(encoding="utf-8")

        vacancy_id = add_vacancy(
            title=args.title,
            company=args.company,
            source_name=args.source,
            source_type=args.source_type,
            source_url=args.url,
            raw_text=raw_text,
            language=args.language,
            remote_format=args.remote_format,
            salary_min=args.salary_min,
            salary_max=args.salary_max,
            salary_currency=args.salary_currency,
            db_path=args.db,
        )
        print(f"Vacancy added: #{vacancy_id}")
        return

    if args.command == "import-vacancy":
        imported = import_vacancy_file(args.path)
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
            db_path=args.db,
        )
        print(f"Vacancy imported: #{vacancy_id}")
        print(f"Title: {imported.title}")
        print(f"Company: {imported.company or '-'}")
        print(f"Source: {imported.source_name} ({imported.source_type})")
        print(f"Language: {imported.language}")
        print(f"Remote: {imported.remote_format}")
        return

    if args.command == "paste-vacancy":
        print("Paste vacancy text below.")
        print("Finish input with Ctrl+Z then Enter in PowerShell, or Ctrl+D in bash.")
        text = sys.stdin.read()
        imported = import_vacancy_text(text, fallback_title=args.title, source_name=args.source)
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
            db_path=args.db,
        )
        print(f"Vacancy pasted: #{vacancy_id}")
        print(f"Title: {imported.title}")
        print(f"Company: {imported.company or '-'}")
        print(f"Source: {imported.source_name} ({imported.source_type})")
        print(f"Language: {imported.language}")
        print(f"Remote: {imported.remote_format}")
        return

    if args.command == "clip-vacancy":
        try:
            text = read_clipboard_text()
        except ClipboardError as error:
            print(f"Clipboard error: {error}")
            return
        imported = import_vacancy_text(text, fallback_title=args.title, source_name=args.source)
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
            db_path=args.db,
        )
        print(f"Vacancy imported from clipboard: #{vacancy_id}")
        print(f"Title: {imported.title}")
        print(f"Company: {imported.company or '-'}")
        print(f"Source: {imported.source_name} ({imported.source_type})")
        print(f"Language: {imported.language}")
        print(f"Remote: {imported.remote_format}")
        return

    if args.command == "paste-analyze":
        print("Paste vacancy text below.")
        print("Finish input with Ctrl+Z then Enter in PowerShell, or Ctrl+D in bash.")
        text = sys.stdin.read()
        imported = import_vacancy_text(text, fallback_title=args.title, source_name=args.source)
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
            db_path=args.db,
        )
        analysis = analyze_vacancy_text(
            title=imported.title,
            raw_text=imported.raw_text,
            remote_format=imported.remote_format,
            salary_min=imported.salary_min,
            salary_currency=imported.salary_currency,
        )
        save_vacancy_analysis(
            vacancy_id=vacancy_id,
            detected_role=analysis.detected_role,
            selected_resume=analysis.selected_resume,
            match_score=analysis.match_score,
            chance=analysis.chance,
            requirements=analysis.requirements,
            flags=analysis.flags,
            db_path=args.db,
        )
        print(f"Vacancy saved and analyzed: #{vacancy_id}")
        print(f"Title: {imported.title}")
        print(f"Company: {imported.company or '-'}")
        print(f"Role: {analysis.detected_role}")
        print(f"Resume: {analysis.selected_resume}")
        print(f"Score: {analysis.match_score}")
        print(f"Chance: {analysis.chance}")
        if analysis.flags:
            print("Flags:")
            for flag in analysis.flags:
                print(f"- [{flag.severity}] {flag.flag_type}: {flag.text}")
        _print_vacancy_card(vacancy_id, args.db)
        return

    if args.command == "clip-analyze":
        try:
            text = read_clipboard_text()
        except ClipboardError as error:
            print(f"Clipboard error: {error}")
            return
        imported = import_vacancy_text(text, fallback_title=args.title, source_name=args.source)
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
            db_path=args.db,
        )
        analysis = analyze_vacancy_text(
            title=imported.title,
            raw_text=imported.raw_text,
            remote_format=imported.remote_format,
            salary_min=imported.salary_min,
            salary_currency=imported.salary_currency,
        )
        save_vacancy_analysis(
            vacancy_id=vacancy_id,
            detected_role=analysis.detected_role,
            selected_resume=analysis.selected_resume,
            match_score=analysis.match_score,
            chance=analysis.chance,
            requirements=analysis.requirements,
            flags=analysis.flags,
            db_path=args.db,
        )
        print(f"Vacancy imported from clipboard and analyzed: #{vacancy_id}")
        print(f"Title: {imported.title}")
        print(f"Company: {imported.company or '-'}")
        print(f"Role: {analysis.detected_role}")
        print(f"Resume: {analysis.selected_resume}")
        print(f"Score: {analysis.match_score}")
        print(f"Chance: {analysis.chance}")
        if analysis.flags:
            print("Flags:")
            for flag in analysis.flags:
                print(f"- [{flag.severity}] {flag.flag_type}: {flag.text}")
        _print_vacancy_card(vacancy_id, args.db)
        return

    if args.command == "list-vacancies":
        rows = list_vacancies(status=args.status, limit=args.limit, db_path=args.db)
        if not rows:
            print("No vacancies found.")
            return

        for row in rows:
            company = row["company"] or "-"
            print(
                f"#{row['id']} | {row['status']} | {row['title']} | "
                f"{company} | chance={row['chance']} | resume={row['selected_resume']}"
            )
        return

    if args.command == "show-vacancy":
        row = get_vacancy(args.id, db_path=args.db)
        if row is None:
            print(f"Vacancy not found: #{args.id}")
            return
        if row["status"] == "new" or row["match_score"] is None:
            analysis = analyze_vacancy_text(
                title=row["title"],
                raw_text=row["raw_text"],
                remote_format=row["remote_format"],
                salary_min=row["salary_min"],
                salary_currency=row["salary_currency"],
                experience_min_years=row["experience_min_years"],
            )
            save_vacancy_analysis(
                vacancy_id=args.id,
                detected_role=analysis.detected_role,
                selected_resume=analysis.selected_resume,
                match_score=analysis.match_score,
                chance=analysis.chance,
                requirements=analysis.requirements,
                flags=analysis.flags,
                db_path=args.db,
            )
            row = get_vacancy(args.id, db_path=args.db)

        _print_vacancy_card(args.id, args.db)
        print("")
        print(f"ID: {row['id']}")
        print(f"Title: {row['title']}")
        print(f"Company: {_display_company(row['company'])}")
        print(f"Source: {row['source_name'] or '-'} ({row['source_type'] or '-'})")
        print(f"URL: {row['source_url'] or '-'}")
        print(f"Language: {row['language']}")
        print(f"Remote: {row['remote_format']}")
        print(f"Salary: {row['salary_min'] or '-'} - {row['salary_max'] or '-'} {row['salary_currency'] or ''}".rstrip())
        print(f"Role: {row['detected_role']}")
        print(f"Resume: {row['selected_resume']}")
        print(f"Chance: {row['chance']}")
        print(f"Score: {row['match_score'] if row['match_score'] is not None else '-'}")
        print(f"Status: {row['status']}")
        print(f"Created: {row['created_at']}")
        flags = get_vacancy_flags(args.id, db_path=args.db)
        if flags:
            print("")
            print("Flags:")
            for flag in flags:
                print(f"- [{flag['severity']}] {flag['flag_type']}: {flag['text']}")
        requirements = get_vacancy_requirements(args.id, db_path=args.db)
        if requirements:
            print("")
            print("Requirements:")
            for requirement in requirements:
                covered = {1: "yes", 0: "no", None: "unknown"}[requirement["is_covered"]]
                evidence = f" ({requirement['evidence']})" if requirement["evidence"] else ""
                print(f"- [{covered}] {requirement['text']}{evidence}")
        if row["raw_text"]:
            print("")
            print("Raw text:")
            print(row["raw_text"])
        return

    if args.command == "analyze-vacancy":
        row = get_vacancy(args.id, db_path=args.db)
        if row is None:
            print(f"Vacancy not found: #{args.id}")
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
            vacancy_id=args.id,
            detected_role=analysis.detected_role,
            selected_resume=analysis.selected_resume,
            match_score=analysis.match_score,
            chance=analysis.chance,
            requirements=analysis.requirements,
            flags=analysis.flags,
            db_path=args.db,
        )

        print(f"Vacancy analyzed: #{args.id}")
        print(f"Role: {analysis.detected_role}")
        print(f"Resume: {analysis.selected_resume}")
        print(f"Score: {analysis.match_score}")
        print(f"Chance: {analysis.chance}")
        if analysis.flags:
            print("Flags:")
            for flag in analysis.flags:
                print(f"- [{flag.severity}] {flag.flag_type}: {flag.text}")
        return

    if args.command == "explain-vacancy":
        row = get_vacancy(args.id, db_path=args.db)
        if row is None:
            print(f"Vacancy not found: #{args.id}")
            return
        if row["status"] == "new" or row["match_score"] is None:
            analysis = analyze_vacancy_text(
                title=row["title"],
                raw_text=row["raw_text"],
                remote_format=row["remote_format"],
                salary_min=row["salary_min"],
                salary_currency=row["salary_currency"],
                experience_min_years=row["experience_min_years"],
            )
            save_vacancy_analysis(
                vacancy_id=args.id,
                detected_role=analysis.detected_role,
                selected_resume=analysis.selected_resume,
                match_score=analysis.match_score,
                chance=analysis.chance,
                requirements=analysis.requirements,
                flags=analysis.flags,
                db_path=args.db,
            )
            row = get_vacancy(args.id, db_path=args.db)
        flags = get_vacancy_flags(args.id, db_path=args.db)
        requirements = get_vacancy_requirements(args.id, db_path=args.db)
        print(build_explanation(row, flags, requirements, load_profile()))
        return

    if args.command == "draft-vacancy":
        row = get_vacancy(args.id, db_path=args.db)
        if row is None:
            print(f"Vacancy not found: #{args.id}")
            return
        if row["status"] == "new" or row["match_score"] is None:
            analysis = analyze_vacancy_text(
                title=row["title"],
                raw_text=row["raw_text"],
                remote_format=row["remote_format"],
                salary_min=row["salary_min"],
                salary_currency=row["salary_currency"],
                experience_min_years=row["experience_min_years"],
            )
            save_vacancy_analysis(
                vacancy_id=args.id,
                detected_role=analysis.detected_role,
                selected_resume=analysis.selected_resume,
                match_score=analysis.match_score,
                chance=analysis.chance,
                requirements=analysis.requirements,
                flags=analysis.flags,
                db_path=args.db,
            )
            row = get_vacancy(args.id, db_path=args.db)

        flags = get_vacancy_flags(args.id, db_path=args.db)
        requirements = get_vacancy_requirements(args.id, db_path=args.db)
        profile = load_profile()
        summary = build_service_summary(row, flags, requirements, profile)
        draft = build_cover_letter_draft(row, flags, requirements, profile)
        application_id = add_application(
            vacancy_id=args.id,
            channel="manual",
            generated_text=draft,
            db_path=args.db,
        )
        print(f"Draft created: application #{application_id}")
        print("")
        print(summary)
        print("")
        print(draft)
        return

    if args.command == "redraft-application":
        application = get_application(args.id, db_path=args.db)
        if application is None:
            print(f"Application not found: #{args.id}")
            return

        row = get_vacancy(application["vacancy_id"], db_path=args.db)
        if row is None:
            print(f"Vacancy not found: #{application['vacancy_id']}")
            return
        if row["status"] == "new" or row["match_score"] is None:
            analysis = analyze_vacancy_text(
                title=row["title"],
                raw_text=row["raw_text"],
                remote_format=row["remote_format"],
                salary_min=row["salary_min"],
                salary_currency=row["salary_currency"],
                experience_min_years=row["experience_min_years"],
            )
            save_vacancy_analysis(
                vacancy_id=row["id"],
                detected_role=analysis.detected_role,
                selected_resume=analysis.selected_resume,
                match_score=analysis.match_score,
                chance=analysis.chance,
                requirements=analysis.requirements,
                flags=analysis.flags,
                db_path=args.db,
            )
            row = get_vacancy(application["vacancy_id"], db_path=args.db)

        flags = get_vacancy_flags(row["id"], db_path=args.db)
        requirements = get_vacancy_requirements(row["id"], db_path=args.db)
        profile = load_profile()
        summary = build_service_summary(row, flags, requirements, profile)
        draft = build_cover_letter_draft(row, flags, requirements, profile)
        updated = update_application_draft_text(args.id, draft, db_path=args.db)
        if not updated:
            print(f"Application not found: #{args.id}")
            return
        print(f"Draft regenerated: application #{args.id}")
        print("Final text and approval were reset. Check the draft again before sending.")
        print("")
        print(summary)
        print("")
        print(draft)
        return

    if args.command == "update-status":
        updated = update_vacancy_status(args.id, args.status, db_path=args.db)
        if updated:
            print(f"Vacancy #{args.id} status updated to {args.status}.")
        else:
            print(f"Vacancy not found: #{args.id}")
        return

    if args.command == "delete-vacancy":
        deleted = delete_vacancy(args.id, db_path=args.db)
        if deleted:
            print(f"Vacancy deleted: #{args.id}")
        else:
            print(f"Vacancy not found: #{args.id}")
        return

    if args.command == "create-application":
        generated_text = (
            args.generated_text_file.read_text(encoding="utf-8")
            if args.generated_text_file
            else None
        )
        final_text = (
            args.final_text_file.read_text(encoding="utf-8")
            if args.final_text_file
            else None
        )
        application_id = add_application(
            vacancy_id=args.vacancy_id,
            channel=args.channel,
            generated_text=generated_text,
            final_text=final_text,
            user_approved=args.approved,
            applied_at=args.applied_at,
            next_followup_at=args.next_followup_at,
            notes=args.notes,
            db_path=args.db,
        )
        if application_id is None:
            print(f"Vacancy not found: #{args.vacancy_id}")
        else:
            print(f"Application created: #{application_id}")
        return

    if args.command == "list-applications":
        rows = list_applications(status=args.status, limit=args.limit, db_path=args.db)
        if not rows:
            print("No applications found.")
            return

        for row in rows:
            company = row["company"] or "-"
            approved = "approved" if row["user_approved"] else "not-approved"
            print(
                f"#{row['id']} | {row['status']} | {row['vacancy_title']} | "
                f"{company} | {_channel_label(row['channel'])} | followup={row['next_followup_at'] or '-'} | {approved}"
            )
        return

    if args.command == "show-application":
        row = get_application(args.id, db_path=args.db)
        if row is None:
            print(f"Application not found: #{args.id}")
            return

        print(f"ID: {row['id']}")
        print(f"Vacancy: #{row['vacancy_id']} {row['vacancy_title']}")
        print(f"Company: {row['company'] or '-'}")
        print(f"URL: {row['source_url'] or '-'}")
        print(f"Status: {row['status']}")
        print(f"Channel: {_channel_label(row['channel'])}")
        print(f"Applied: {row['applied_at'] or '-'}")
        print(f"Next follow-up: {row['next_followup_at'] or '-'}")
        print(f"Approved: {'yes' if row['user_approved'] else 'no'}")
        if row["notes"]:
            print(f"Notes: {row['notes']}")
        if row["generated_text"]:
            print("")
            print("Generated text:")
            print(row["generated_text"])
        if row["final_text"]:
            print("")
            print("Final text:")
            print(row["final_text"])
        events = list_contact_events(application_id=args.id, limit=3, db_path=args.db)
        if events:
            print("")
            print("Last events:")
            for event in events:
                print(_format_event(event))
        return

    if args.command == "application-history":
        row = get_application(args.id, db_path=args.db)
        if row is None:
            print(f"Application not found: #{args.id}")
            return
        events = list_contact_events(application_id=args.id, limit=args.limit, db_path=args.db)
        if not events:
            print("No history events.")
            return
        print(f"History for application #{args.id}: {row['vacancy_title']}")
        for event in events:
            print(_format_event(event))
        return

    if args.command == "add-note":
        event_id = add_contact_event(
            application_id=args.id,
            event_type="note",
            direction="internal",
            text=args.text,
            db_path=args.db,
        )
        if event_id is None:
            print(f"Application not found: #{args.id}")
        else:
            print(f"Note added: event #{event_id}")
        return

    if args.command == "add-event":
        direction = "inbound" if args.event_type in {"reply", "interview", "rejection", "offer"} else "internal"
        event_id = add_contact_event(
            application_id=args.id,
            event_type=args.event_type,
            direction=direction,
            text=args.text,
            db_path=args.db,
        )
        if event_id is None:
            print(f"Application not found: #{args.id}")
        else:
            next_status = _status_for_event(args.event_type)
            if next_status:
                update_application_status(args.id, next_status, db_path=args.db)
            print(f"Event added: #{event_id}")
        return

    if args.command == "check-application":
        row = get_application(args.id, db_path=args.db)
        if row is None:
            print(f"Application not found: #{args.id}")
            return
        print(format_application_check(check_application_text(row)))
        return

    if args.command == "update-application-status":
        updated = update_application_status(args.id, args.status, db_path=args.db)
        if updated:
            print(f"Application #{args.id} status updated to {args.status}.")
        else:
            print(f"Application not found: #{args.id}")
        return

    if args.command == "approve-application":
        approved = approve_application(args.id, db_path=args.db)
        if approved:
            print(f"Application approved: #{args.id}")
        else:
            print(f"Application not found: #{args.id}")
        return

    if args.command == "mark-sent":
        sent = mark_application_sent(
            application_id=args.id,
            channel=args.channel,
            applied_at=args.applied_at,
            next_followup_at=args.next_followup_at,
            db_path=args.db,
        )
        if sent:
            add_contact_event(
                application_id=args.id,
                event_type="application",
                direction="outbound",
                text="Отклик отправлен.",
                event_at=args.applied_at,
                db_path=args.db,
            )
            print(f"Application marked as sent: #{args.id}")
        else:
            print(f"Application not found: #{args.id}")
        return

    if args.command == "delete-application":
        deleted = delete_application(args.id, db_path=args.db)
        if deleted:
            print(f"Application deleted: #{args.id}")
        else:
            print(f"Application not found: #{args.id}")
        return

    if args.command == "export-draft":
        row = get_application(args.id, db_path=args.db)
        if row is None:
            print(f"Application not found: #{args.id}")
            return
        text = row["final_text"] or row["generated_text"]
        if not text:
            print("Application has no draft text.")
            return
        path = DEFAULT_DB_PATH.parents[1] / "data" / "drafts" / f"application_{args.id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Draft exported: {path}")
        return

    if args.command == "open-edit":
        row = get_application(args.id, db_path=args.db)
        if row is None:
            print(f"Application not found: #{args.id}")
            return
        text = row["final_text"] or row["generated_text"]
        if not text:
            print("Application has no draft text.")
            return
        path = DEFAULT_DB_PATH.parents[1] / "data" / "drafts" / f"application_{args.id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Draft exported: {path}")
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            print("Opened in default editor. Save the file, then run import-final.")
        except OSError as error:
            print(f"Could not open editor: {error}")
            print(f"Open manually: {path}")
        return

    if args.command == "import-final":
        path = DEFAULT_DB_PATH.parents[1] / "data" / "drafts" / f"application_{args.id}.txt"
        if not path.exists():
            print(f"Draft file not found: {path}")
            return
        final_text = path.read_text(encoding="utf-8").strip()
        if not final_text:
            print("Draft file is empty. Not imported.")
            return
        updated = update_application_final_text(args.id, final_text, db_path=args.db)
        if updated:
            print(f"Final text imported: #{args.id}")
        else:
            print(f"Application not found: #{args.id}")
        return

    if args.command == "due-followups":
        rows = list_due_followups(due_date=args.date, db_path=args.db)
        if not rows:
            print("No due follow-ups.")
            return

        for row in rows:
            company = row["company"] or "-"
            print(
                f"#{row['id']} | due={row['next_followup_at']} | {row['vacancy_title']} | "
                f"{company} | {_channel_label(row['channel'])} | status={row['status']}"
            )
        return

    parser.error(f"Unknown command: {args.command}")


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


def _print_quick_review(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        return
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    print(build_quick_review(row, flags, requirements, load_profile()))


def _print_vacancy_card(vacancy_id: int, db_path: Path) -> None:
    row = get_vacancy(vacancy_id, db_path=db_path)
    if row is None:
        return
    flags = get_vacancy_flags(vacancy_id, db_path=db_path)
    requirements = get_vacancy_requirements(vacancy_id, db_path=db_path)
    print(build_vacancy_card(row, flags, requirements, load_profile()))


def _display_company(value: str | None) -> str:
    if not value:
        return "-"
    lowered = value.lower().replace("ё", "е")
    looks_like_salary = (
        any(char.isdigit() for char in lowered)
        and any(marker in lowered for marker in ("до", "от", "зарплат", "доход", "salary", "руб", "rub", "usd", "₽", "$", "€"))
    )
    return "-" if looks_like_salary else value


def _status_for_event(event_type: str) -> str | None:
    return {
        "followup": "followed_up",
        "interview": "interview",
        "rejection": "rejected",
        "offer": "offer",
    }.get(event_type)


if __name__ == "__main__":
    main()

