from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SOURCE_TYPE_ALIASES = {
    "hh": "hh",
    "hh.ru": "hh",
    "headhunter": "hh",
    "linkedin": "linkedin",
    "telegram": "telegram",
    "tg": "telegram",
    "remote": "remote_board",
    "remote board": "remote_board",
    "freelance": "freelance",
    "upwork": "freelance",
    "kwork": "freelance",
    "company": "company_site",
    "company site": "company_site",
    "сайт компании": "company_site",
    "manual": "manual",
    "вручную": "manual",
}

REMOTE_ALIASES = {
    "remote": "remote",
    "удаленка": "remote",
    "удалёнка": "remote",
    "удаленно": "remote",
    "удалённо": "remote",
    "hybrid": "hybrid",
    "гибрид": "hybrid",
    "office": "office",
    "офис": "office",
    "relocation": "relocation",
    "релокация": "relocation",
}

HEADER_ALIASES = {
    "url": "url",
    "link": "url",
    "ссылка": "url",
    "источник": "source",
    "source": "source",
    "компания": "company",
    "company": "company",
    "название": "title",
    "позиция": "title",
    "title": "title",
    "role": "title",
    "зарплата": "salary",
    "salary": "salary",
    "формат": "remote_format",
    "format": "remote_format",
    "язык": "language",
    "language": "language",
}


@dataclass(frozen=True)
class ImportedVacancy:
    title: str
    company: str | None
    source_name: str
    source_type: str
    source_url: str | None
    raw_text: str
    language: str
    remote_format: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None


def import_vacancy_file(path: Path) -> ImportedVacancy:
    text = path.read_text(encoding="utf-8-sig").strip()
    return import_vacancy_text(text, fallback_title=_clean_filename_title(path.stem), source_name=None)


def import_vacancy_text(
    text: str,
    *,
    fallback_title: str = "Pasted vacancy",
    source_name: str | None = None,
) -> ImportedVacancy:
    text = _repair_mojibake(text.strip())
    if not text:
        raise ValueError("Vacancy text is empty.")

    headers = _parse_headers(text)
    body = _extract_body(text)

    title = headers.get("title") or _guess_title(body) or fallback_title
    company = headers.get("company") or _guess_company(body)
    resolved_source_name = headers.get("source") or source_name or _guess_source_name(text) or "manual"
    source_type = _normalize_source_type(resolved_source_name)
    source_url = headers.get("url") or _guess_url(text)
    language = _normalize_language(headers.get("language")) or _detect_language(text)
    remote_format = _normalize_remote(headers.get("remote_format")) or _guess_remote(text)
    salary_min, salary_max, salary_currency = _parse_salary(headers.get("salary") or text)

    return ImportedVacancy(
        title=title,
        company=company,
        source_name=resolved_source_name,
        source_type=source_type,
        source_url=source_url,
        raw_text=text,
        language=language,
        remote_format=remote_format,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
    )


def _parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(("текст вакансии", "vacancy text", "description")):
            break
        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        normalized_key = HEADER_ALIASES.get(key.strip().lower())
        value = value.strip()
        if normalized_key and value:
            headers[normalized_key] = value
    return headers


def _extract_body(text: str) -> str:
    marker_pattern = re.compile(r"^\s*(текст вакансии|vacancy text|description)\s*:\s*$", re.IGNORECASE)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if marker_pattern.match(line):
            return "\n".join(lines[index + 1 :]).strip()
    return text.strip()


def _guess_title(text: str) -> str | None:
    title_markers = (
        "вакансия",
        "vacancy",
        "позиция",
        "position",
        "должность",
        "role",
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith(title_markers) and ":" in stripped:
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value[:160]
        if _looks_like_heading(stripped):
            return stripped[:160]
    return None


def _guess_company(text: str) -> str | None:
    company_markers = (
        "компания",
        "company",
        "работодатель",
        "employer",
    )
    for line in text.splitlines()[:30]:
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if key.strip().lower() in company_markers and value.strip():
            return value.strip()[:160]
    top_lines = [line.strip() for line in text.splitlines()[:6] if line.strip()]
    if len(top_lines) >= 2 and _looks_like_heading(top_lines[1]):
        return top_lines[1][:160]
    return None


def _looks_like_heading(line: str) -> bool:
    lowered = line.lower().replace("ё", "е")
    if _looks_like_salary_line(lowered):
        return False
    metadata_lines = {
        "удаленно",
        "удаленка",
        "remote",
        "офис",
        "гибрид",
        "hybrid",
        "office",
        "полная занятость",
        "частичная занятость",
    }
    if lowered.strip(" .:-") in metadata_lines:
        return False
    skip_prefixes = (
        "http",
        "ссылка",
        "источник",
        "уровень дохода",
        "опыт работы",
        "полная занятость",
        "частичная занятость",
        "зарплата",
        "формат",
        "формат работы",
        "график",
        "рабочие часы",
        "сейчас эту вакансию смотр",
        "язык",
        "основные задачи",
        "задачи",
        "обязанности",
        "требования",
        "условия",
        "мы предлагаем",
        "about",
        "responsibilities",
        "requirements",
    )
    if lowered.startswith(skip_prefixes):
        return False
    if len(line) > 160:
        return False
    return bool(re.search(r"[A-Za-zА-Яа-яЁё]", line))


def _looks_like_salary_line(lowered: str) -> bool:
    return bool(
        re.search(r"(\d[\d\s]{2,}|₽|\$|€|\bруб\b|\brub\b|\busd\b|\beur\b)", lowered)
        and any(marker in lowered for marker in ("до", "от", "зарплат", "доход", "salary", "руб", "rub", "usd", "₽", "$", "€"))
    )


def _clean_filename_title(stem: str) -> str:
    return re.sub(r"[_-]+", " ", stem).strip() or "Untitled vacancy"


def _guess_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    if not match:
        return None
    return match.group(0).rstrip(").,;")


def _guess_source_name(text: str) -> str | None:
    url = _guess_url(text)
    if not url:
        return None
    lowered = url.lower()
    if "hh.ru" in lowered:
        return "hh"
    if "linkedin.com" in lowered:
        return "linkedin"
    if "t.me" in lowered or "telegram" in lowered:
        return "telegram"
    if "upwork.com" in lowered:
        return "upwork"
    if "kwork.ru" in lowered:
        return "kwork"
    return None


def _normalize_source_type(source_name: str) -> str:
    source = source_name.strip().lower()
    return SOURCE_TYPE_ALIASES.get(source, "other")


def _normalize_language(language: str | None) -> str | None:
    if not language:
        return None
    value = language.strip().lower()
    if value in {"ru", "rus", "russian", "русский"}:
        return "ru"
    if value in {"en", "eng", "english", "английский"}:
        return "en"
    if value in {"mixed", "mix", "смешанный"}:
        return "mixed"
    return "unknown"


def _detect_language(text: str) -> str:
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyrillic and latin and min(cyrillic, latin) / max(cyrillic, latin) > 0.25:
        return "mixed"
    if cyrillic > latin:
        return "ru"
    if latin > cyrillic:
        return "en"
    return "unknown"


def _normalize_remote(remote_format: str | None) -> str | None:
    if not remote_format:
        return None
    value = remote_format.strip().lower()
    return REMOTE_ALIASES.get(value, "unknown")


def _guess_remote(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    if any(word in lowered for word in ("удаленно", "удалённо", "удаленка", "удалёнка", "удаленная", "удалённая", "remote")):
        return "remote"
    if any(word in lowered for word in ("гибрид", "hybrid")):
        return "hybrid"
    if any(word in lowered for word in ("офис", "office")):
        return "office"
    if any(word in lowered for word in ("релокация", "relocation")):
        return "relocation"
    return "unknown"


def _parse_salary(text: str) -> tuple[int | None, int | None, str | None]:
    currency = _guess_currency(text)
    without_urls = re.sub(r"https?://\S+", " ", text)
    normalized = without_urls.replace("\u00a0", " ")
    numbers = [
        int(match.replace(" ", ""))
        for match in re.findall(r"(?<!\d)(\d{2,3}(?:\s?\d{3})+|\d{4,6})(?!\d)", normalized)
    ]

    if not numbers:
        return None, None, currency

    if len(numbers) == 1:
        return numbers[0], None, currency

    return min(numbers[:2]), max(numbers[:2]), currency


def _guess_currency(text: str) -> str | None:
    lowered = text.lower()
    if "₽" in lowered or re.search(r"(?<![а-яa-z])(руб(?:\.|лей|ля|ль)?|rub)(?![а-яa-z])", lowered):
        return "RUB"
    if "$" in lowered or re.search(r"(?<![а-яa-z])(usd|доллар(?:ов|а)?)(?![а-яa-z])", lowered):
        return "USD"
    if "€" in lowered or re.search(r"(?<![а-яa-z])(eur|euro)(?![а-яa-z])", lowered):
        return "EUR"
    return None


def _repair_mojibake(text: str) -> str:
    # PowerShell pipes can occasionally hand Python UTF-8 text decoded as cp1251.
    # The result is recognizable Russian mojibake such as "РЈРґР°...".
    markers = ("РЈ", "Рґ", "Р°", "Р»", "СЃ", "С‚", "Рё", "РЅ", "Рµ", "Рѕ")
    marker_count = sum(text.count(marker) for marker in markers)
    if marker_count < 5:
        return text

    candidates: list[str] = []
    for errors in ("strict", "ignore", "replace"):
        try:
            candidates.append(text.encode("cp1251", errors=errors).decode("utf-8", errors=errors))
        except UnicodeError:
            continue

    if not candidates:
        return text

    def quality(value: str) -> tuple[int, int]:
        repaired_markers = sum(value.count(marker) for marker in markers)
        cyrillic = len(re.findall(r"[А-Яа-яЁё]", value))
        return (-repaired_markers, cyrillic)

    best = max(candidates, key=quality)
    return best if quality(best) > quality(text) else text

