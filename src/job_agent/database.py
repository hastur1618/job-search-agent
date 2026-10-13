from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "job_agent.sqlite"
SCHEMA_PATH = PROJECT_ROOT / "src" / "job_agent" / "schema.sql"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(db_path) as connection:
        connection.executescript(schema)


def get_db_info(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    if not db_path.exists():
        return {}

    query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """

    with connect(db_path) as connection:
        tables = [row["name"] for row in connection.execute(query).fetchall()]
        return {
            table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in tables
        }


def add_vacancy(
    *,
    title: str,
    company: str | None = None,
    source_name: str | None = None,
    source_type: str = "manual",
    source_url: str | None = None,
    raw_text: str | None = None,
    language: str = "unknown",
    remote_format: str = "unknown",
    salary_min: int | None = None,
    salary_max: int | None = None,
    salary_currency: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    with connect(db_path) as connection:
        company_id = None
        if company:
            connection.execute(
                "INSERT OR IGNORE INTO companies (name) VALUES (?);",
                (company,),
            )
            company_id = connection.execute(
                "SELECT id FROM companies WHERE name = ?;",
                (company,),
            ).fetchone()["id"]

        source_id = None
        if source_name:
            connection.execute(
                """
                INSERT OR IGNORE INTO sources (name, source_type, url)
                VALUES (?, ?, ?);
                """,
                (source_name, source_type, source_url),
            )
            source_id = connection.execute(
                "SELECT id FROM sources WHERE name = ?;",
                (source_name,),
            ).fetchone()["id"]

        cursor = connection.execute(
            """
            INSERT INTO vacancies (
                title,
                company_id,
                source_id,
                source_url,
                raw_text,
                language,
                remote_format,
                salary_min,
                salary_max,
                salary_currency
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                title,
                company_id,
                source_id,
                source_url,
                raw_text,
                language,
                remote_format,
                salary_min,
                salary_max,
                salary_currency,
            ),
        )
        return int(cursor.lastrowid)


def list_vacancies(
    *,
    status: str | None = None,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE vacancies.status = ?"
        params.append(status)

    params.append(limit)

    query = f"""
        SELECT
            vacancies.id,
            vacancies.title,
            companies.name AS company,
            vacancies.status,
            vacancies.chance,
            vacancies.selected_resume,
            vacancies.created_at
        FROM vacancies
        LEFT JOIN companies ON companies.id = vacancies.company_id
        {where}
        ORDER BY vacancies.created_at DESC, vacancies.id DESC
        LIMIT ?;
    """

    with connect(db_path) as connection:
        return connection.execute(query, params).fetchall()


def get_vacancy(vacancy_id: int, db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    query = """
        SELECT
            vacancies.*,
            companies.name AS company,
            sources.name AS source_name,
            sources.source_type AS source_type
        FROM vacancies
        LEFT JOIN companies ON companies.id = vacancies.company_id
        LEFT JOIN sources ON sources.id = vacancies.source_id
        WHERE vacancies.id = ?;
    """

    with connect(db_path) as connection:
        return connection.execute(query, (vacancy_id,)).fetchone()


def find_duplicate_vacancy(
    *,
    title: str,
    company: str | None = None,
    source_url: str | None = None,
    raw_text: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> sqlite3.Row | None:
    normalized_title = _normalize_duplicate_text(title)
    normalized_company = _normalize_duplicate_text(company or "")
    normalized_raw_text = _normalize_duplicate_text(raw_text or "")
    normalized_url = (source_url or "").strip().rstrip("/")

    with connect(db_path) as connection:
        if normalized_url:
            row = connection.execute(
                """
                SELECT
                    vacancies.id,
                    vacancies.title,
                    companies.name AS company,
                    vacancies.source_url,
                    vacancies.raw_text,
                    vacancies.chance,
                    vacancies.match_score,
                    vacancies.status,
                    vacancies.created_at
                FROM vacancies
                LEFT JOIN companies ON companies.id = vacancies.company_id
                WHERE rtrim(vacancies.source_url, '/') = ?
                ORDER BY vacancies.created_at DESC, vacancies.id DESC
                LIMIT 1;
                """,
                (normalized_url,),
            ).fetchone()
            if row is not None:
                return row

        rows = connection.execute(
            """
            SELECT
                vacancies.id,
                vacancies.title,
                companies.name AS company,
                vacancies.source_url,
                vacancies.raw_text,
                vacancies.chance,
                vacancies.match_score,
                vacancies.status,
                vacancies.created_at
            FROM vacancies
            LEFT JOIN companies ON companies.id = vacancies.company_id
            ORDER BY vacancies.created_at DESC, vacancies.id DESC
            LIMIT 200;
            """
        ).fetchall()

    for row in rows:
        existing_raw_text = _normalize_duplicate_text(row["raw_text"] or "")
        if normalized_raw_text and len(normalized_raw_text) >= 40 and normalized_raw_text == existing_raw_text:
            return row

        existing_title = _normalize_duplicate_text(row["title"] or "")
        existing_company = _normalize_duplicate_text(row["company"] or "")
        if normalized_title and normalized_title == existing_title:
            if normalized_company and normalized_company == existing_company:
                return row
            if not normalized_company and normalized_raw_text and existing_raw_text:
                if _raw_text_overlap(normalized_raw_text, existing_raw_text):
                    return row

    return None


def get_vacancy_flags(vacancy_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return connection.execute(
            """
            SELECT flag_type, severity, text
            FROM vacancy_flags
            WHERE vacancy_id = ?
            ORDER BY
                CASE severity
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                id;
            """,
            (vacancy_id,),
        ).fetchall()


def get_vacancy_requirements(vacancy_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return connection.execute(
            """
            SELECT requirement_type, text, is_covered, evidence
            FROM vacancy_requirements
            WHERE vacancy_id = ?
            ORDER BY id;
            """,
            (vacancy_id,),
        ).fetchall()


def add_application(
    *,
    vacancy_id: int,
    channel: str = "manual",
    generated_text: str | None = None,
    final_text: str | None = None,
    user_approved: bool = False,
    applied_at: str | None = None,
    next_followup_at: str | None = None,
    notes: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int | None:
    with connect(db_path) as connection:
        vacancy = connection.execute(
            "SELECT id FROM vacancies WHERE id = ?;",
            (vacancy_id,),
        ).fetchone()
        if vacancy is None:
            return None

        cursor = connection.execute(
            """
            INSERT INTO applications (
                vacancy_id,
                applied_at,
                channel,
                status,
                generated_text,
                final_text,
                user_approved,
                next_followup_at,
                last_contact_at,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                vacancy_id,
                applied_at,
                channel,
                "sent" if applied_at else "draft",
                generated_text,
                final_text,
                int(user_approved),
                next_followup_at,
                applied_at,
                notes,
            ),
        )
        if applied_at:
            connection.execute(
                """
                UPDATE vacancies
                SET status = 'applied', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (vacancy_id,),
            )
        return int(cursor.lastrowid)


def list_applications(
    *,
    status: str | None = None,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE applications.status = ?"
        params.append(status)
    params.append(limit)

    query = f"""
        SELECT
            applications.id,
            applications.status,
            applications.channel,
            applications.applied_at,
            applications.next_followup_at,
            applications.user_approved,
            vacancies.title AS vacancy_title,
            companies.name AS company
        FROM applications
        JOIN vacancies ON vacancies.id = applications.vacancy_id
        LEFT JOIN companies ON companies.id = vacancies.company_id
        {where}
        ORDER BY applications.created_at DESC, applications.id DESC
        LIMIT ?;
    """
    with connect(db_path) as connection:
        return connection.execute(query, params).fetchall()


def get_application(application_id: int, db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    query = """
        SELECT
            applications.*,
            vacancies.title AS vacancy_title,
            vacancies.source_url AS source_url,
            vacancies.salary_min AS salary_min,
            vacancies.salary_max AS salary_max,
            vacancies.salary_currency AS salary_currency,
            vacancies.detected_role AS detected_role,
            vacancies.chance AS vacancy_chance,
            vacancies.match_score AS vacancy_match_score,
            companies.name AS company
        FROM applications
        JOIN vacancies ON vacancies.id = applications.vacancy_id
        LEFT JOIN companies ON companies.id = vacancies.company_id
        WHERE applications.id = ?;
    """
    with connect(db_path) as connection:
        return connection.execute(query, (application_id,)).fetchone()


def update_application_status(
    application_id: int,
    status: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE applications
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (status, application_id),
        )
        return cursor.rowcount > 0


def approve_application(application_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE applications
            SET
                user_approved = 1,
                final_text = COALESCE(final_text, generated_text),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (application_id,),
        )
        return cursor.rowcount > 0


def mark_application_sent(
    *,
    application_id: int,
    channel: str,
    applied_at: str,
    next_followup_at: str | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT vacancy_id FROM applications WHERE id = ?;",
            (application_id,),
        ).fetchone()
        if row is None:
            return False

        connection.execute(
            """
            UPDATE applications
            SET
                status = 'sent',
                channel = ?,
                applied_at = ?,
                last_contact_at = ?,
                next_followup_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (channel, applied_at, applied_at, next_followup_at, application_id),
        )
        connection.execute(
            """
            UPDATE vacancies
            SET status = 'applied', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (row["vacancy_id"],),
        )
        return True


def add_contact_event(
    *,
    application_id: int,
    event_type: str,
    direction: str = "internal",
    text: str | None = None,
    notes: str | None = None,
    event_at: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int | None:
    with connect(db_path) as connection:
        application = connection.execute(
            "SELECT id FROM applications WHERE id = ?;",
            (application_id,),
        ).fetchone()
        if application is None:
            return None

        cursor = connection.execute(
            """
            INSERT INTO contact_events (
                application_id,
                event_type,
                event_at,
                direction,
                text,
                notes
            )
            VALUES (?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?);
            """,
            (application_id, event_type, event_at, direction, text, notes),
        )
        return int(cursor.lastrowid)


def list_contact_events(
    *,
    application_id: int,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    query = """
        SELECT id, event_type, event_at, direction, text, notes
        FROM contact_events
        WHERE application_id = ?
        ORDER BY datetime(event_at) DESC, id DESC
        LIMIT ?;
    """
    with connect(db_path) as connection:
        return connection.execute(query, (application_id, limit)).fetchall()


def update_application_final_text(
    application_id: int,
    final_text: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE applications
            SET final_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (final_text, application_id),
        )
        return cursor.rowcount > 0


def update_application_draft_text(
    application_id: int,
    generated_text: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE applications
            SET
                generated_text = ?,
                final_text = NULL,
                user_approved = 0,
                status = 'draft',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (generated_text, application_id),
        )
        return cursor.rowcount > 0


def delete_application(application_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM applications WHERE id = ?;",
            (application_id,),
        )
        return cursor.rowcount > 0


def list_due_followups(
    *,
    due_date: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            applications.id,
            applications.status,
            applications.channel,
            applications.next_followup_at,
            vacancies.title AS vacancy_title,
            companies.name AS company,
            vacancies.source_url AS source_url
        FROM applications
        JOIN vacancies ON vacancies.id = applications.vacancy_id
        LEFT JOIN companies ON companies.id = vacancies.company_id
        WHERE applications.next_followup_at IS NOT NULL
          AND date(applications.next_followup_at) <= date(?)
          AND applications.status NOT IN ('rejected', 'closed', 'offer')
        ORDER BY applications.next_followup_at ASC, applications.id ASC;
    """
    with connect(db_path) as connection:
        return connection.execute(query, (due_date,)).fetchall()


def list_unsent_applications(
    *,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            applications.id,
            applications.status,
            applications.channel,
            applications.user_approved,
            applications.final_text,
            applications.generated_text,
            vacancies.title AS vacancy_title,
            vacancies.chance AS chance,
            vacancies.match_score AS match_score,
            companies.name AS company
        FROM applications
        JOIN vacancies ON vacancies.id = applications.vacancy_id
        LEFT JOIN companies ON companies.id = vacancies.company_id
        WHERE applications.status = 'draft'
        ORDER BY applications.updated_at DESC, applications.id DESC
        LIMIT ?;
    """
    with connect(db_path) as connection:
        return connection.execute(query, (limit,)).fetchall()


def list_vacancies_without_applications(
    *,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            vacancies.id,
            vacancies.title,
            vacancies.status,
            vacancies.chance,
            vacancies.match_score,
            companies.name AS company
        FROM vacancies
        LEFT JOIN companies ON companies.id = vacancies.company_id
        WHERE vacancies.status IN ('new', 'analyzed')
          AND NOT EXISTS (
              SELECT 1
              FROM applications
              WHERE applications.vacancy_id = vacancies.id
          )
        ORDER BY
            CASE vacancies.chance
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            vacancies.updated_at DESC,
            vacancies.id DESC
        LIMIT ?;
    """
    with connect(db_path) as connection:
        return connection.execute(query, (limit,)).fetchall()


def save_vacancy_analysis(
    *,
    vacancy_id: int,
    detected_role: str,
    selected_resume: str,
    match_score: int,
    chance: str,
    requirements: list[object],
    flags: list[object],
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE vacancies
            SET
                detected_role = ?,
                selected_resume = ?,
                match_score = ?,
                chance = ?,
                status = CASE
                    WHEN status = 'new' THEN 'analyzed'
                    ELSE status
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (detected_role, selected_resume, match_score, chance, vacancy_id),
        )
        if cursor.rowcount == 0:
            return False

        connection.execute("DELETE FROM vacancy_requirements WHERE vacancy_id = ?;", (vacancy_id,))
        connection.execute("DELETE FROM vacancy_flags WHERE vacancy_id = ?;", (vacancy_id,))

        connection.executemany(
            """
            INSERT INTO vacancy_requirements (vacancy_id, requirement_type, text, is_covered, evidence)
            VALUES (?, ?, ?, ?, ?);
            """,
            [
                (
                    vacancy_id,
                    requirement.requirement_type,
                    requirement.text,
                    None if requirement.is_covered is None else int(requirement.is_covered),
                    requirement.evidence,
                )
                for requirement in requirements
            ],
        )
        connection.executemany(
            """
            INSERT INTO vacancy_flags (vacancy_id, flag_type, severity, text)
            VALUES (?, ?, ?, ?);
            """,
            [
                (vacancy_id, flag.flag_type, flag.severity, flag.text)
                for flag in flags
            ],
        )
        return True


def update_vacancy_status(
    vacancy_id: int,
    status: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE vacancies
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (status, vacancy_id),
        )
        return cursor.rowcount > 0


def delete_vacancy(vacancy_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    with connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM vacancies WHERE id = ?;",
            (vacancy_id,),
        )
        return cursor.rowcount > 0


def cleanup_empty_references(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    with connect(db_path) as connection:
        companies = connection.execute(
            """
            DELETE FROM companies
            WHERE id NOT IN (
                SELECT DISTINCT company_id
                FROM vacancies
                WHERE company_id IS NOT NULL
            );
            """
        ).rowcount
        sources = connection.execute(
            """
            DELETE FROM sources
            WHERE id NOT IN (
                SELECT DISTINCT source_id
                FROM vacancies
                WHERE source_id IS NOT NULL
            );
            """
        ).rowcount
        return {"companies": companies, "sources": sources}


def _normalize_duplicate_text(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^\wа-яА-Я]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _raw_text_overlap(left: str, right: str) -> bool:
    if len(left) < 40 or len(right) < 40:
        return False
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens)) >= 0.85

