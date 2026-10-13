from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "data" / "profile.yaml"


@dataclass(frozen=True)
class CandidateProfile:
    english_level: str = "B1"
    english_speaking: str = "basic"
    years_experience: float = 1.5
    remote_only: bool = True
    relocation: bool = False
    salary_targets: dict[str, dict[str, int]] | None = None
    strengths: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> CandidateProfile:
    if not path.exists():
        return CandidateProfile()

    text = path.read_text(encoding="utf-8")
    return CandidateProfile(
        english_level=_read_scalar(text, "level", default="B1", parent="english"),
        english_speaking=_read_scalar(text, "speaking", default="basic", parent="english"),
        years_experience=float(_read_scalar(text, "years", default="1.5", parent="experience")),
        remote_only=_read_bool(text, "remote_only", default=True),
        relocation=_read_bool(text, "relocation", default=False),
        salary_targets=_read_salary_targets(text),
        strengths=tuple(_read_list(text, "strengths")),
        limits=tuple(_read_list(text, "limits")),
    )


def _read_scalar(text: str, key: str, *, default: str, parent: str | None = None) -> str:
    lines = _section_lines(text, parent) if parent else text.splitlines()
    prefix = f"{key}:"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.split(":", 1)[1].strip()
    return default


def _read_bool(text: str, key: str, *, default: bool) -> bool:
    value = _read_scalar(text, key, default=str(default).lower())
    return value.lower() in {"true", "yes", "1"}


def _read_list(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    result: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith(f"{key}:"):
            in_section = True
            continue
        if in_section and line and not line.startswith(" "):
            break
        if in_section:
            stripped = line.strip()
            if stripped.startswith("- "):
                result.append(stripped[2:].strip())
    return result


def _read_salary_targets(text: str) -> dict[str, dict[str, int]]:
    targets: dict[str, dict[str, int]] = {}
    section = _section_lines(text, "salary_targets")
    current_role: str | None = None
    for line in section:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith(("rub_", "usd_")):
            current_role = stripped[:-1]
            targets[current_role] = {}
            continue
        if current_role and ":" in stripped:
            key, value = stripped.split(":", 1)
            try:
                targets[current_role][key.strip()] = int(value.strip())
            except ValueError:
                continue
    return targets


def _section_lines(text: str, section: str | None) -> list[str]:
    if not section:
        return text.splitlines()
    lines = text.splitlines()
    result: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith(f"{section}:"):
            in_section = True
            continue
        if in_section and line and not line.startswith(" "):
            break
        if in_section:
            result.append(line)
    return result

