from __future__ import annotations

import re
from dataclasses import dataclass


KNOWN_SKILLS = {
    "python",
    "javascript",
    "js",
    "n8n",
    "openai",
    "api",
    "rest",
    "json",
    "google sheets",
    "google docs",
    "google drive",
    "telegram",
    "github",
    "git",
    "excel",
    "ahrefs",
    "semrush",
    "majestic",
    "netpeak",
    "a-parser",
    "xrumеr",
    "xrumer",
    "seo",
    "link building",
    "outreach",
    "аутрич",
    "переговор",
    "guest posting",
    "линкбилдинг",
    "igaming",
    "gambling",
    "гемблинг",
    "casino",
    "betting",
    "prompt",
    "llm",
    "rag",
}

ROLE_KEYWORDS = {
    "ai_automation": [
        "ai automation",
        "automation",
        "автоматизац",
        "n8n",
        "python",
        "openai",
        "llm",
        "api",
        "workflow",
        "интеграц",
        "rag",
        "prompt",
    ],
    "outreach": [
        "outreach",
        "аутрич",
        "webmaster",
        "вебмастер",
        "guest post",
        "guest posting",
        "sponsored post",
        "переговор",
        "линкбилдинг",
    ],
    "link_builder": [
        "link builder",
        "link building",
        "линкбилдер",
        "off-page",
        "offpage",
        "seo",
        "crowd",
        "крауд",
        "донор",
        "ahrefs",
        "netpeak",
        "xrumеr",
        "xrumer",
        "a-parser",
    ],
    "ai_rater": [
        "ai data annotator",
        "data annotator",
        "ai trainer",
        "search quality rater",
        "ads quality rater",
        "language specialist",
        "russian speaker",
        "разметка",
        "аннотац",
        "оценщик",
    ],
}

SALARY_TARGETS = {
    "ai_automation": {"RUB": 100000, "USD_MONTH": 2000, "USD_HOUR": 15},
    "outreach": {"RUB": 80000, "USD_MONTH": 1300, "USD_HOUR": 8},
    "link_builder": {"RUB": 80000, "USD_MONTH": 1000, "USD_HOUR": 6},
    "ai_rater": {"RUB": 80000, "USD_MONTH": 1000, "USD_HOUR": 6},
}


@dataclass(frozen=True)
class Requirement:
    requirement_type: str
    text: str
    is_covered: bool | None
    evidence: str | None = None


@dataclass(frozen=True)
class Flag:
    flag_type: str
    severity: str
    text: str


@dataclass(frozen=True)
class VacancyAnalysis:
    detected_role: str
    selected_resume: str
    match_score: int
    chance: str
    requirements: list[Requirement]
    flags: list[Flag]


def analyze_vacancy_text(
    *,
    title: str,
    raw_text: str | None,
    remote_format: str,
    salary_min: int | None,
    salary_currency: str | None,
    experience_min_years: float | None = None,
) -> VacancyAnalysis:
    text = f"{title}\n{raw_text or ''}"
    lowered = text.lower()

    role_scores = _score_roles(lowered)
    detected_role = max(role_scores, key=role_scores.get)
    if role_scores[detected_role] == 0:
        detected_role = "other"

    selected_resume = _select_resume(detected_role)
    requirements = _extract_requirements(raw_text or "")
    flags = _detect_flags(
        lowered=lowered,
        detected_role=detected_role,
        remote_format=remote_format,
        salary_min=salary_min,
        salary_currency=salary_currency,
        experience_min_years=experience_min_years,
    )

    covered = sum(1 for requirement in requirements if requirement.is_covered is True)
    missing = sum(1 for requirement in requirements if requirement.is_covered is False)
    score = _calculate_score(
        role_score=role_scores.get(detected_role, 0),
        covered=covered,
        missing=missing,
        flags=flags,
    )
    chance = _chance_from_score(score, flags)

    return VacancyAnalysis(
        detected_role=detected_role,
        selected_resume=selected_resume,
        match_score=score,
        chance=chance,
        requirements=requirements,
        flags=flags,
    )


def _score_roles(lowered: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for role, keywords in ROLE_KEYWORDS.items():
        scores[role] = sum(1 for keyword in keywords if keyword in lowered)
    return scores


def _select_resume(detected_role: str) -> str:
    if detected_role in {"ai_automation", "outreach", "link_builder"}:
        return detected_role
    if detected_role == "ai_rater":
        return "ai_automation"
    return "none"


def _extract_requirements(raw_text: str) -> list[Requirement]:
    requirements: list[Requirement] = []
    current_type: str | None = None

    for line in raw_text.splitlines():
        stripped = line.strip(" \t-*•")
        if not stripped:
            continue

        lowered = stripped.lower()
        if _is_section_header(lowered, ("основные задачи", "задачи", "обязанности", "responsibilities")):
            current_type = "responsibility"
            continue
        if _is_section_header(lowered, ("требования", "requirements", "must have", "we expect")):
            current_type = "must_have"
            continue
        if _is_section_header(lowered, ("будет плюсом", "плюсом", "nice to have", "bonus")):
            current_type = "nice_to_have"
            continue
        if _is_section_header(
            lowered,
            (
                "мы предлагаем",
                "условия",
                "conditions",
                "ключевые навыки",
                "задайте вопрос",
                "где предстоит работать",
            ),
        ):
            current_type = None

        if current_type and len(stripped) >= 3:
            covered, evidence = _coverage_for_requirement(stripped)
            requirements.append(
                Requirement(
                    requirement_type=current_type,
                    text=stripped[:500],
                    is_covered=covered,
                    evidence=evidence,
                )
            )

    return requirements[:30]


def _is_section_header(lowered: str, markers: tuple[str, ...]) -> bool:
    normalized = lowered.strip(" :.-")
    return any(normalized == marker or normalized.startswith(f"{marker}:") for marker in markers)


def _coverage_for_requirement(text: str) -> tuple[bool | None, str | None]:
    lowered = text.lower()
    matched = sorted(skill for skill in KNOWN_SKILLS if _skill_matches(skill, lowered))
    if matched:
        return True, ", ".join(matched[:5])

    hard_missing = (
        "c1",
        "c2",
        "fluent",
        "свободн",
        "4+",
        "5+",
        "senior",
        "team lead",
        "ci/cd",
        "kubernetes",
        "docker",
    )
    if any(marker in lowered for marker in hard_missing):
        return False, None

    return None, None


def _skill_matches(skill: str, lowered: str) -> bool:
    if not skill.isascii():
        return skill in lowered
    escaped = re.escape(skill.lower())
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", lowered))


def _detect_flags(
    *,
    lowered: str,
    detected_role: str,
    remote_format: str,
    salary_min: int | None,
    salary_currency: str | None,
    experience_min_years: float | None,
) -> list[Flag]:
    flags: list[Flag] = []

    if remote_format in {"office", "relocation"}:
        flags.append(Flag("remote", "high", "Формат не подходит: офис или релокация."))

    if any(marker in lowered for marker in ("только офис", "office only", "релокация обязательна")):
        flags.append(Flag("remote", "high", "В тексте есть признак обязательного офиса или релокации."))

    experience = experience_min_years or _guess_experience(lowered)
    if experience and experience >= 3:
        flags.append(Flag("experience", "medium", f"Требуется опыт от {experience:g} лет, это выше текущего уровня."))

    if any(marker in lowered for marker in ("b2", "upper-intermediate", "upper intermediate", "c1", "c2", "fluent english", "свободный английский", "английский c1")):
        flags.append(Flag("language", "medium", "Английский выше текущего профиля B1 или требует уверенного Upper-Intermediate."))

    if any(marker in lowered for marker in ("предоплат", "оплата обучения", "купить курс", "вступительный взнос", "доход без опыта")):
        flags.append(Flag("scam", "high", "Есть мошеннический или рискованный признак: предоплата, обучение за деньги или доход без опыта."))

    salary_flag = _salary_flag(detected_role, salary_min, salary_currency)
    if salary_flag:
        flags.append(salary_flag)

    if detected_role == "other":
        flags.append(Flag("note", "medium", "Роль не похожа на основные направления: AI automation, outreach, link builder или AI rater."))

    return flags


def _guess_experience(lowered: str) -> float | None:
    patterns = (
        r"от\s+(\d+(?:[.,]\d+)?)\s+лет",
        r"(\d+(?:[.,]\d+)?)\s*[–-]\s*\d+(?:[.,]\d+)?\s+(?:года|лет)",
        r"(\d+(?:[.,]\d+)?)\+?\s+years",
        r"experience\s+(\d+(?:[.,]\d+)?)\+?",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def _salary_flag(detected_role: str, salary_min: int | None, salary_currency: str | None) -> Flag | None:
    if salary_min is None or not salary_currency:
        return None

    targets = SALARY_TARGETS.get(detected_role)
    if not targets:
        return None

    currency = salary_currency.upper()
    if currency == "RUB" and salary_min < targets["RUB"]:
        return Flag("salary", "medium", f"Нижняя граница зарплаты {salary_min} RUB ниже цели для направления.")

    if currency == "USD" and salary_min < targets["USD_HOUR"]:
        return Flag("salary", "low", f"USD-ставка или сумма начинается ниже ориентира для направления.")

    return None


def _calculate_score(*, role_score: int, covered: int, missing: int, flags: list[Flag]) -> int:
    score = 35 + min(role_score * 8, 35) + min(covered * 5, 20) - min(missing * 8, 24)
    for flag in flags:
        if flag.severity == "high":
            score -= 30
        elif flag.severity == "medium":
            score -= 15
        elif flag.severity == "low":
            score -= 7
    return max(0, min(100, score))


def _chance_from_score(score: int, flags: list[Flag]) -> str:
    if any(flag.severity == "high" and flag.flag_type in {"scam", "remote"} for flag in flags):
        return "skip"
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "low"
    return "skip"

