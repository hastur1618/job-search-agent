from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckIssue:
    severity: str
    text: str


@dataclass(frozen=True)
class ApplicationCheck:
    verdict: str
    source: str
    issues: list[CheckIssue]
    text_length: int

    @property
    def can_send(self) -> bool:
        return self.verdict == "ok"


SERVICE_LINE_RE = re.compile(
    r"^(резюме|язык письма|совпадение|флаги|шансы|профиль):",
    re.IGNORECASE | re.MULTILINE,
)

PLACEHOLDER_RE = re.compile(
    r"(\[.+?\]|<.+?>|впиши|todo|заполни|замени)",
    re.IGNORECASE,
)

UNSAFE_CLAIMS_RE = re.compile(
    r"(native english|fluent english|c2|c1|senior|эксперт|свободно владею|носитель)",
    re.IGNORECASE,
)


def check_application_text(application: sqlite3.Row) -> ApplicationCheck:
    final_text = (application["final_text"] or "").strip()
    generated_text = (application["generated_text"] or "").strip()
    text = final_text or generated_text
    source = "final_text" if final_text else "generated_text"

    issues: list[CheckIssue] = []
    if not text:
        return ApplicationCheck(
            verdict="needs_work",
            source=source,
            issues=[CheckIssue("high", "Нет текста отклика.")],
            text_length=0,
        )

    if not final_text:
        issues.append(
            CheckIssue(
                "medium",
                "Финальный текст ещё не импортирован. Сейчас проверяется сгенерированный черновик.",
            )
        )

    if SERVICE_LINE_RE.search(text):
        issues.append(
            CheckIssue(
                "high",
                "В тексте есть служебный блок анализа. Его нельзя отправлять работодателю.",
            )
        )

    if PLACEHOLDER_RE.search(text):
        issues.append(
            CheckIssue(
                "high",
                "В тексте остались плейсхолдеры или технические пометки.",
            )
        )

    if len(text) < 250:
        issues.append(CheckIssue("medium", "Отклик выглядит слишком коротким."))
    if len(text) > 2500:
        issues.append(CheckIssue("medium", "Отклик выглядит слишком длинным для первого сообщения."))

    first_lines = "\n".join(text.splitlines()[:3]).lower()
    if not any(greeting in first_lines for greeting in ("здравствуйте", "добрый", "hi", "hello")):
        issues.append(CheckIssue("low", "Не найдено нормальное приветствие в начале."))

    lower_text = text.lower()
    if application["salary_min"] is None and application["salary_max"] is None:
        if not any(word in lower_text for word in ("зарплат", "вилк", "оплат", "salary", "compensation")):
            issues.append(
                CheckIssue(
                    "low",
                    "В вакансии не указана зарплата, но в отклике нет вопроса про вилку.",
                )
            )

    role = application["detected_role"] or ""
    role_markers = {
        "ai_automation": ("n8n", "python", "api", "llm", "автоматизац"),
        "outreach": ("outreach", "аутрич", "webmaster", "вебмастер", "гостев"),
        "link_builder": ("link", "линк", "donor", "донор", "seo"),
    }
    markers = role_markers.get(role, ())
    if markers and not any(marker in lower_text for marker in markers):
        issues.append(
            CheckIssue(
                "medium",
                "Текст слабо связан с выбранной ролью и может выглядеть шаблонно.",
            )
        )

    if UNSAFE_CLAIMS_RE.search(text):
        issues.append(
            CheckIssue(
                "medium",
                "Есть сильные заявления про уровень или seniority. Лучше проверить, что они не преувеличивают профиль.",
            )
        )

    if application["status"] == "sent" and not application["user_approved"]:
        issues.append(
            CheckIssue(
                "high",
                "Отклик отмечен отправленным, но не отмечен как одобренный.",
            )
        )

    high_count = sum(1 for issue in issues if issue.severity == "high")
    medium_count = sum(1 for issue in issues if issue.severity == "medium")
    verdict = "ok" if high_count == 0 and medium_count <= 2 else "needs_work"
    return ApplicationCheck(verdict=verdict, source=source, issues=issues, text_length=len(text))


def format_application_check(check: ApplicationCheck) -> str:
    verdict = "можно отправлять" if check.can_send else "нужно доработать"
    source = {
        "generated_text": "сгенерированный черновик",
        "final_text": "финальный текст",
    }.get(check.source, check.source)
    lines = [
        f"Вердикт: {verdict}",
        f"Источник текста: {source}",
        f"Длина: {check.text_length} символов",
    ]
    if not check.issues:
        lines.append("Проблем не найдено.")
        return "\n".join(lines)

    lines.append("Замечания:")
    for issue in check.issues:
        severity = {
            "high": "важно",
            "medium": "средне",
            "low": "мелочь",
        }.get(issue.severity, issue.severity)
        lines.append(f"- [{severity}] {issue.text}")
    return "\n".join(lines)
