from __future__ import annotations

import re
import sqlite3

from job_agent.profile import CandidateProfile


RESUME_LABELS = {
    "ai_automation": "AI Automation Specialist",
    "outreach": "Outreach Manager",
    "link_builder": "Link Builder",
    "none": "nearest relevant resume",
    "unknown": "nearest relevant resume",
}


def build_cover_letter_draft(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile | None = None,
) -> str:
    profile = profile or CandidateProfile()
    language = vacancy["language"]
    if language == "en":
        return _build_en(vacancy, flags, requirements, profile)
    return _build_ru(vacancy, flags, requirements, profile)


def build_service_summary(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile | None = None,
) -> str:
    profile = profile or CandidateProfile()
    covered = [row["text"] for row in requirements if row["is_covered"] == 1]
    missing = [row["text"] for row in requirements if row["is_covered"] == 0]
    unknown = [row["text"] for row in requirements if row["is_covered"] is None]
    flag_text = "; ".join(f"{row['severity']}: {row['text']}" for row in flags) or "нет явных флагов"

    return "\n".join(
        [
            f"Резюме: {RESUME_LABELS.get(vacancy['selected_resume'], vacancy['selected_resume'])}.",
            f"Язык письма: {'английский' if vacancy['language'] == 'en' else 'русский'}.",
            f"Совпадение: закрыто {len(covered)}, пробелов {len(missing)}, неясно {len(unknown)}.",
            f"Флаги: {flag_text}.",
            f"Шансы: {vacancy['chance']} при score={vacancy['match_score']}.",
            f"Профиль: опыт {profile.years_experience}+ года, английский {profile.english_level}, формат только удалённо.",
        ]
    )


def _build_ru(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    role = vacancy["detected_role"]
    covered = _covered_keywords(requirements)
    cautions = _caution_sentences(flags, profile)
    raw_text = (vacancy["raw_text"] or "").lower()
    focus_tasks = _focus_tasks_ru(vacancy, requirements)
    bridge = _experience_bridge_ru(role, focus_tasks, raw_text)

    if role == "ai_automation":
        body = [
            "Здравствуйте.",
            f"Хочу откликнуться на вакансию {vacancy['title']}. По описанию мне особенно близки задачи: {focus_tasks}.",
            bridge,
        ]
    elif role == "outreach":
        body = [
            "Здравствуйте.",
            f"Хочу откликнуться на вакансию {vacancy['title']}. Вижу в описании задачи, которые хорошо пересекаются с моим текущим опытом: {focus_tasks}.",
            bridge,
        ]
    elif role == "link_builder":
        body = [
            "Здравствуйте.",
            f"Хочу откликнуться на вакансию {vacancy['title']}. Больше всего зацепили задачи: {focus_tasks}.",
            bridge,
        ]
    else:
        body = [
            "Здравствуйте.",
            f"Хочу откликнуться на вакансию {vacancy['title']}. По описанию вижу пересечение с моим опытом: {focus_tasks}.",
            bridge,
        ]

    if covered:
        body.append(f"Из требований особенно совпадает: {covered}.")
    if _mentions_ai_search(raw_text):
        body.append("Отдельно интересен блок AI Search: у меня есть практический опыт с n8n, Python и LLM API, поэтому тема AI Overviews и видимости в AI-системах мне близка.")
    body.extend(cautions)
    if vacancy["salary_min"] is None and vacancy["salary_max"] is None:
        body.append("По условиям хотел бы отдельно уточнить зарплатную вилку.")
    questions = _questions_ru(vacancy, raw_text)
    if questions:
        body.append(questions)
    body.append("Если формат и ожидания по опыту подходят, готов обсудить детали в чате или на коротком созвоне.")
    return "\n".join(body)


def _build_en(
    vacancy: sqlite3.Row,
    flags: list[sqlite3.Row],
    requirements: list[sqlite3.Row],
    profile: CandidateProfile,
) -> str:
    role = vacancy["detected_role"]
    covered = _covered_keywords(requirements)
    cautions = _caution_sentences_en(flags, profile)
    raw_text = (vacancy["raw_text"] or "").lower()
    focus_tasks = _focus_tasks_en(vacancy, requirements)
    bridge = _experience_bridge_en(role, focus_tasks, raw_text)

    if role == "ai_automation":
        body = [
            "Hi.",
            f"I would like to apply for {vacancy['title']}. The parts that look closest to my experience are: {focus_tasks}.",
            bridge,
        ]
    elif role == "outreach":
        body = [
            "Hi.",
            f"I would like to apply for {vacancy['title']}. The role matches my current experience in these areas: {focus_tasks}.",
            bridge,
        ]
    elif role == "link_builder":
        body = [
            "Hi.",
            f"I would like to apply for {vacancy['title']}. The most relevant parts for me are: {focus_tasks}.",
            bridge,
        ]
    else:
        body = [
            "Hi.",
            f"I would like to apply for {vacancy['title']}. I see overlap with my experience in: {focus_tasks}.",
            bridge,
        ]

    if covered:
        body.append(f"The closest match is: {covered}.")
    if _mentions_ai_search(raw_text):
        body.append("The AI Search part is especially interesting to me: I have hands-on experience with n8n, Python and LLM APIs.")
    body.extend(cautions)
    if vacancy["salary_min"] is None and vacancy["salary_max"] is None:
        body.append("I would also like to clarify the salary range.")
    questions = _questions_en(vacancy, raw_text)
    if questions:
        body.append(questions)
    body.append("If my background fits, I would be glad to discuss the details.")
    return "\n".join(body)


def _covered_keywords(requirements: list[sqlite3.Row]) -> str:
    items = [row["evidence"] or row["text"] for row in requirements if row["is_covered"] == 1]
    cleaned: list[str] = []
    for item in items:
        for part in item.split(","):
            value = part.strip()
            if value and value not in cleaned:
                cleaned.append(value)
    return ", ".join(cleaned[:6])


def _focus_tasks_ru(vacancy: sqlite3.Row, requirements: list[sqlite3.Row]) -> str:
    tasks = _task_candidates(vacancy, requirements)
    if tasks:
        return "; ".join(tasks[:3])

    role = vacancy["detected_role"]
    if role == "ai_automation":
        return "автоматизация процессов, работа с API и LLM-инструментами, сборка рабочих сценариев"
    if role == "outreach":
        return "поиск площадок, переговоры о размещениях, оценка доноров и работа с SEO-командой"
    if role == "link_builder":
        return "подбор доноров, размещение ссылок, работа с SEO-метриками и таблицами"
    return "SEO, линкбилдинг, автоматизация и работа с AI-инструментами"


def _focus_tasks_en(vacancy: sqlite3.Row, requirements: list[sqlite3.Row]) -> str:
    tasks = _task_candidates(vacancy, requirements)
    if tasks:
        return "; ".join(tasks[:3])

    role = vacancy["detected_role"]
    if role == "ai_automation":
        return "process automation, API work, LLM tools and workflow building"
    if role == "outreach":
        return "finding websites, negotiating placements, checking donors and working with SEO teams"
    if role == "link_builder":
        return "donor research, link placements, SEO metrics and spreadsheet work"
    return "SEO, link building, automation and AI tools"


def _task_candidates(vacancy: sqlite3.Row, requirements: list[sqlite3.Row]) -> list[str]:
    rows = [
        row["text"]
        for row in requirements
        if row["requirement_type"] in {"responsibility", "must_have"} and len(row["text"]) >= 12
    ]
    if rows:
        return _clean_tasks(rows)

    raw_text = vacancy["raw_text"] or ""
    section_lines = _extract_section_lines(
        raw_text,
        start_markers=(
            "основные задачи",
            "задачи",
            "обязанности",
            "чем предстоит заниматься",
            "responsibilities",
            "what you will do",
        ),
        stop_markers=(
            "требования",
            "для успешного",
            "будет плюсом",
            "мы предлагаем",
            "условия",
            "requirements",
            "nice to have",
        ),
    )
    if len(section_lines) < 2:
        section_lines.extend(
            _extract_section_lines(
                raw_text,
                start_markers=("требования", "для успешного", "requirements", "must have"),
                stop_markers=("будет плюсом", "мы предлагаем", "условия", "nice to have", "we offer"),
            )
        )
    return _clean_tasks(section_lines)


def _extract_section_lines(
    raw_text: str,
    *,
    start_markers: tuple[str, ...],
    stop_markers: tuple[str, ...],
) -> list[str]:
    result: list[str] = []
    in_section = False
    for line in raw_text.splitlines():
        stripped = line.strip(" \t-*•")
        if not stripped:
            continue
        lowered = stripped.lower().strip(" :.-")
        if any(lowered == marker or lowered.startswith(f"{marker}:") for marker in start_markers):
            in_section = True
            continue
        if in_section and any(lowered == marker or lowered.startswith(f"{marker}:") for marker in stop_markers):
            break
        if in_section:
            result.append(stripped)
    return result


def _clean_tasks(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        value = re.sub(r"\s+", " ", line).strip(" .;")
        if len(value) < 12 or len(value) > 180:
            continue
        if value.lower().startswith(("мы ", "we ", "компания ", "our ")):
            continue
        if value not in result:
            result.append(value)
    return result[:3]


def _experience_bridge_ru(role: str, focus_tasks: str, raw_text: str) -> str:
    if role == "ai_automation":
        return "Из практического опыта могу быть полезен в автоматизации рутины: работал с n8n, Python, OpenAI API, Telegram Bot API, Google Sheets, Docs и Drive, собирал сценарии и скрипты для обработки данных и списков страниц."
    if role == "outreach":
        return "Сейчас работаю Link Builder в SEO/линкбилдинг-агентстве: ищу площадки, веду переписку, договариваюсь о размещениях, оцениваю доноров и работаю с iGaming-проектами."
    if role == "link_builder":
        return "Сейчас занимаюсь линкбилдингом: краудом, аутричем, подбором площадок, проверкой доноров и размещениями для casino, betting и iGaming-проектов."
    if "ai search" in raw_text or "llm" in raw_text:
        return "Дополнительно близка тема AI Search и LLM-систем: я работаю с n8n, Python и LLM API, поэтому понимаю, как можно соединять SEO-задачи и автоматизацию."
    return "Сейчас работаю Link Builder и параллельно развиваю автоматизацию на n8n и Python, поэтому могу закрывать задачи на стыке SEO, данных и AI-инструментов."


def _experience_bridge_en(role: str, focus_tasks: str, raw_text: str) -> str:
    if role == "ai_automation":
        return "I can be useful in automation work: I have hands-on experience with n8n, Python, OpenAI API, Telegram Bot API, Google Sheets, Docs and Drive."
    if role == "outreach":
        return "I currently work as a Link Builder in an SEO/link-building agency: I find websites, communicate with webmasters, negotiate placements, check donors and work with iGaming projects."
    if role == "link_builder":
        return "I currently do link building: crowd placements, outreach, site research, donor checks and placements for casino, betting and iGaming projects."
    if "ai search" in raw_text or "llm" in raw_text:
        return "The AI Search and LLM part is also close to me: I work with n8n, Python and LLM APIs, so I understand how SEO tasks can connect with automation."
    return "I currently work as a Link Builder and also build automations with n8n and Python, so I can help with tasks at the intersection of SEO, data and AI tools."


def _questions_ru(vacancy: sqlite3.Row, raw_text: str) -> str:
    questions: list[str] = []
    if "kpi" in raw_text or "метрик" in raw_text or "эффектив" in raw_text:
        questions.append("какие KPI считаются ключевыми на первые 1-2 месяца")
    if "ai search" in raw_text or "ai overview" in raw_text or "llm" in raw_text:
        questions.append("как сейчас измеряете видимость в AI Search/LLM-системах")
    if not questions:
        return ""
    return "Буду рад уточнить: " + "; ".join(questions[:2]) + "."


def _questions_en(vacancy: sqlite3.Row, raw_text: str) -> str:
    questions: list[str] = []
    if "kpi" in raw_text or "metric" in raw_text or "performance" in raw_text:
        questions.append("which KPIs are most important during the first 1-2 months")
    if "ai search" in raw_text or "ai overview" in raw_text or "llm" in raw_text:
        questions.append("how you currently measure visibility in AI Search/LLM systems")
    if not questions:
        return ""
    return "I would also like to clarify: " + "; ".join(questions[:2]) + "."


def _caution_sentences(flags: list[sqlite3.Row], profile: CandidateProfile) -> list[str]:
    texts = [row["text"] for row in flags if row["flag_type"] in {"experience", "language", "salary"}]
    if not texts:
        return []
    result: list[str] = []
    if any("опыт" in text.lower() for text in texts):
        result.append(f"По опыту честно: у меня больше {profile.years_experience} года практики, поэтому если нужен строго более senior-уровень, это может быть ограничением.")
    if any("англий" in text.lower() for text in texts):
        result.append(f"Английский использую в письменной работе, текущий уровень {profile.english_level}, разговорный уровень {profile.english_speaking}.")
    return result


def _caution_sentences_en(flags: list[sqlite3.Row], profile: CandidateProfile) -> list[str]:
    texts = [row["text"] for row in flags if row["flag_type"] in {"experience", "language", "salary"}]
    if not texts:
        return []
    result: list[str] = []
    if any("experience" in text.lower() or "опыт" in text.lower() for text in texts):
        result.append(f"To be clear about experience: I have {profile.years_experience}+ years of hands-on work, so a strict senior requirement may be a gap.")
    if any("english" in text.lower() or "англий" in text.lower() for text in texts):
        result.append(f"I use English for written work; my current level is {profile.english_level}, and speaking is {profile.english_speaking}.")
    return result


def _mentions_ai_search(raw_text: str) -> bool:
    return any(marker in raw_text for marker in ("ai search", "ai overview", "ai overviews", "llm-систем", "llm-систем"))

