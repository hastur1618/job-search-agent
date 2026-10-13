# Changelog

## 0.1.1 - Duplicate Detection

- Added duplicate vacancy detection before saving imported, pasted, clipboard, and manually added vacancies.
- Existing vacancies are now shown instead of creating another record when the source URL, full vacancy text, or title/company signature matches.
- Added duplicate protection to both CLI and interactive workflows.

## 0.1.0 - Local MVP

- Added a local SQLite tracker for vacancies, applications, requirements, flags, and contact events.
- Added terminal and menu-based workflows for pasting, analyzing, drafting, checking, approving, and tracking applications.
- Added clipboard-based vacancy import for faster daily use on Windows.
- Added rule-based vacancy analysis with role detection, chance scoring, red flags, and resume selection.
- Added profile-aware cover-letter draft generation and pre-send validation.
- Added application history, notes, contact events, follow-up tracking, and a daily next-action summary.
- Added vacancy decision cards with recommendation, rationale, risks, response focus, employer question, and next commands.
- Added safer public-repository defaults by ignoring the local database, drafts, secrets, private profile, and resume files.
