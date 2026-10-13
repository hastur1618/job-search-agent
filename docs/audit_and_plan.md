# AI Agent For Job Search

## What The Existing Materials Already Do Well

The materials are useful. They are not random notes: they already describe a working product direction.

Strong parts:

- Clear target roles: AI automation, outreach manager, link builder, plus AI rater and annotator roles.
- Good factual constraints: do not invent experience, do not use placeholders, do not overstate English or Git level.
- Good tone rules: short, human, no generic AI phrases, no fake enthusiasm.
- Good output format: resume choice, language, match, flags, chances, then the actual text.
- Good red-flag logic: office-only, too much experience, salary below target, suspicious payments, paid training, equipment fees.
- Useful follow-up rules and templates.
- A tracker schema already exists and can become the database model.

## Honest Problems And Gaps

1. The current Obsidian location does not contain the zip file.

The requested path `C:\obsidian\my-obsidian-vault\Вакансии.zip` does not exist. There is a folder `C:\obsidian\my-obsidian-vault\Вакансии`, and I used it as the source. If the zip is meant to be the canonical source, it should be restored or regenerated.

2. The prompt references six resume files, but the current Obsidian folder only has Markdown files.

The main prompt says that six resume files are attached: three Russian and three English versions. They are not present in the current folder. The agent cannot safely enforce "facts only from resume" unless the resumes are stored in the project as machine-readable inputs.

Fix:

- Put resumes into `data/resumes/`.
- Convert each resume to structured JSON/YAML facts.
- Keep original DOCX/PDF only as source artifacts.

3. There are many `[ВПИШИ ...]` and one `[ВСТАВЬ ...]` placeholders.

Missing fields:

- why you are looking for work
- when you can start
- acceptable contract format
- comfortable working hours
- project workload while employed
- test-task policy
- how you receive foreign payments
- 1-2 real writing samples

These must become required profile fields. Until filled, the agent should ask you before generating answers that need them.

4. The main prompt is too large to use as one system prompt forever.

It is good as a human spec, but too monolithic for an application. If used as one giant prompt, it will be harder to test, harder to update, and easier for the model to miss details.

Better split:

- `profile`: facts about you
- `resumes`: structured resume facts and salary targets
- `rules`: tone, language, honesty, salary logic
- `scoring`: match and red-flag rules
- `templates`: follow-ups and recruiter messages
- `validators`: checks before output

5. The agent is described as if it already has RAG, Telegram, HeadHunter API, Google Sheets, and Python.

That is fine as a roadmap, but for the MVP it is too much at once. RAG should not be first. A structured fact store is enough for the first version.

Best MVP:

- paste vacancy text or load from a local sample
- parse vacancy
- choose resume direction
- score match and red flags
- draft response
- run validator
- save application to local tracker

Then add HH API, Google Sheets, Telegram, and RAG.

6. Some company and platform lists are unverified.

Several companies have `?`, empty status, or unknown remote status. This is useful as a lead list, not as truth. The agent should store them as leads with `verification_status`, not as reliable facts.

7. Duplicate files should be removed or archived.

Files marked by the notes as removable:

- `Меня игнорят после собеса.md`
- `План общения с рекрутером.md`
- `Сервисы для работы из дома.md`
- `Удаленка.md`

They duplicate consolidated files and will confuse a retrieval system.

8. The tracker is too small for an agent.

The current tracker is a good start, but the agent needs more fields:

- source URL
- source platform
- salary range
- remote format
- detected language
- selected resume
- match score
- red flags
- generated draft
- user-approved final text
- follow-up due date
- last action timestamp
- rejection reason
- notes

9. Sending applications automatically would be risky.

The agent should not auto-apply or auto-message recruiters in MVP. It should draft and track, but final sending must stay manual until the outputs are consistently good.

10. Security is missing.

The project will use APIs and personal data, so it needs:

- `.env` for secrets
- `.env.example` without real keys
- no tokens in Git
- local encrypted storage later if needed
- personal data not sent to tools unless required

## What To Remove

Remove from the active knowledge base:

- duplicate files that explicitly say they can be deleted
- old prompt versions if newer prompt exists
- company/platform entries that have no status after they are moved into a structured lead table

Do not delete permanently at first. Move old files into `archive/` or mark them as `inactive`.

## What To Add

Add these files/configs:

- `profile.yaml`: contacts, location, English level, work preferences, missing answers
- `resumes/*.yaml`: structured facts for AI automation, outreach, link builder
- `rules/tone.yaml`: tone and forbidden phrases
- `rules/scoring.yaml`: match, red flags, scam signals, salary logic
- `templates/followups.yaml`: RU/EN follow-up templates
- `data/applications.sqlite`: local tracker
- `data/leads.csv`: companies and platforms with verification status
- `tests/fixtures/vacancies/`: sample vacancies in RU and EN

## Recommended Architecture

Modules:

- `job_agent.sources`: vacancy input adapters
- `job_agent.parser`: vacancy text parsing
- `job_agent.profile`: load profile and resume facts
- `job_agent.matcher`: choose resume and calculate fit
- `job_agent.risk`: detect red flags and scam signals
- `job_agent.generator`: create cover letters, replies, follow-ups
- `job_agent.validator`: check language, facts, length, placeholders, forbidden phrases
- `job_agent.tracker`: save applications and follow-up dates
- `job_agent.cli`: command-line interface

Storage:

- SQLite for applications
- YAML/JSON for profile, rules, resumes
- optional Google Sheets sync later

LLM usage:

- One LLM call for structured vacancy parsing if regex is not enough
- One LLM call for drafting
- Deterministic Python validation after drafting

## MVP Workflow

1. User pastes vacancy text or provides a local text file.
2. Agent detects language, role, platform, salary, remote format, requirements, nice-to-have skills.
3. Agent chooses one resume direction: AI automation, outreach, link builder, or closest match.
4. Agent calculates match:
   - covered requirements
   - missing requirements
   - red flags
   - scam signals
   - chance: high, medium, low
5. If critical profile facts are missing, agent asks up to two questions.
6. Agent drafts response in the vacancy language.
7. Validator checks:
   - no `[ВПИШИ]` or `[ADD]`
   - no unsupported facts
   - no forbidden phrases
   - correct language
   - correct salary logic
   - length within target
   - no markdown for messages
8. User approves or edits.
9. Agent saves the application and follow-up date.

## Development Plan

### Stage 1: Clean Knowledge Base

- Move current Obsidian materials into `docs/source_review/` or keep links to source.
- Convert prompt into structured config.
- Add missing profile answers.
- Add actual resume files or structured resume facts.

Result: no duplicate instructions, no missing facts hidden inside one giant prompt.

### Stage 2: Local Python MVP

- Build CLI:
  - `analyze-vacancy`
  - `draft-cover`
  - `draft-followup`
  - `add-application`
  - `list-followups`
- Add SQLite tracker.
- Add validator tests.

Result: useful local tool without integrations.

### Stage 3: Vacancy Sources

- Start with manual paste and saved text files.
- Add HeadHunter API adapter.
- Add import from Telegram/channel text manually.
- Add remote boards only where allowed by their terms.

Result: agent can collect leads but still asks before applying.

### Stage 4: Telegram Bot

- Commands:
  - `/analyze`
  - `/draft`
  - `/followups`
  - `/status`
- Send notifications for follow-up due dates.
- Keep approval step before sending any text externally.

Result: usable daily workflow.

### Stage 5: Google Sheets Sync

- Sync applications table with Google Sheets.
- Keep SQLite as local source of truth or define Sheets as source of truth, but not both ambiguously.

Result: easy human-visible tracker.

### Stage 6: RAG

Add RAG only after structured facts work.

Use it for:

- finding relevant project examples
- pulling exact resume facts
- retrieving past approved replies

Do not use RAG for:

- inventing missing experience
- replacing strict profile/resume facts

## First Implementation Tasks

1. Create structured profile and resume YAML files.
2. Build vacancy parser output schema.
3. Build match and red-flag scoring.
4. Build draft generator prompt from structured pieces.
5. Build validator.
6. Build local tracker.
7. Add tests with 5-10 sample vacancies.

## My Recommendation

Do not start with a "full agent" that searches everywhere, sends messages, runs Telegram, syncs Sheets, and uses RAG. That will become fragile quickly.

Start with a strict local assistant that turns one vacancy into:

- selected resume
- match analysis
- red flags
- chance score
- draft response
- tracker row
- follow-up date

Once this is reliable, integrations become much easier.

