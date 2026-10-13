PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    niche TEXT,
    website_url TEXT,
    remote_status TEXT CHECK (remote_status IN ('unknown', 'remote', 'hybrid', 'office', 'no_remote')) DEFAULT 'unknown',
    verification_status TEXT CHECK (verification_status IN ('unverified', 'checked', 'outdated')) DEFAULT 'unverified',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN ('hh', 'linkedin', 'telegram', 'remote_board', 'freelance', 'company_site', 'manual', 'other')),
    url TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    source_url TEXT,
    raw_text TEXT,
    language TEXT CHECK (language IN ('ru', 'en', 'mixed', 'unknown')) DEFAULT 'unknown',
    employment_type TEXT,
    remote_format TEXT CHECK (remote_format IN ('unknown', 'remote', 'hybrid', 'office', 'relocation')) DEFAULT 'unknown',
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT,
    experience_min_years REAL,
    detected_role TEXT CHECK (detected_role IN ('ai_automation', 'outreach', 'link_builder', 'ai_rater', 'other', 'unknown')) DEFAULT 'unknown',
    selected_resume TEXT CHECK (selected_resume IN ('ai_automation', 'outreach', 'link_builder', 'none', 'unknown')) DEFAULT 'unknown',
    match_score INTEGER CHECK (match_score BETWEEN 0 AND 100),
    chance TEXT CHECK (chance IN ('high', 'medium', 'low', 'skip', 'unknown')) DEFAULT 'unknown',
    status TEXT NOT NULL CHECK (
        status IN (
            'new',
            'analyzed',
            'drafted',
            'applied',
            'waiting',
            'ignored',
            'hr_interview',
            'technical_interview',
            'offer',
            'rejected',
            'closed',
            'skipped'
        )
    ) DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vacancy_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    requirement_type TEXT NOT NULL CHECK (requirement_type IN ('must_have', 'nice_to_have', 'responsibility', 'unknown')),
    text TEXT NOT NULL,
    is_covered INTEGER CHECK (is_covered IN (0, 1)),
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vacancy_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    flag_type TEXT NOT NULL CHECK (flag_type IN ('red_flag', 'scam', 'missing_skill', 'salary', 'remote', 'experience', 'language', 'note')),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high')) DEFAULT 'info',
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    applied_at TEXT,
    channel TEXT CHECK (channel IN ('hh', 'email', 'telegram', 'linkedin', 'form', 'freelance', 'manual', 'other')) DEFAULT 'manual',
    status TEXT NOT NULL CHECK (
        status IN (
            'draft',
            'sent',
            'waiting',
            'followed_up',
            'ignored',
            'interview',
            'offer',
            'rejected',
            'closed'
        )
    ) DEFAULT 'draft',
    generated_text TEXT,
    final_text TEXT,
    user_approved INTEGER NOT NULL CHECK (user_approved IN (0, 1)) DEFAULT 0,
    next_followup_at TEXT,
    last_contact_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    name TEXT,
    role TEXT,
    email TEXT,
    telegram TEXT,
    linkedin_url TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('application', 'followup', 'reply', 'interview', 'rejection', 'offer', 'note')),
    event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    direction TEXT CHECK (direction IN ('outbound', 'inbound', 'internal')) DEFAULT 'internal',
    text TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'vacancy', 'application', 'contact', 'source')),
    entity_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies(status);
CREATE INDEX IF NOT EXISTS idx_vacancies_company_id ON vacancies(company_id);
CREATE INDEX IF NOT EXISTS idx_vacancies_source_id ON vacancies(source_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_next_followup_at ON applications(next_followup_at);
CREATE INDEX IF NOT EXISTS idx_contact_events_application_id ON contact_events(application_id);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);

