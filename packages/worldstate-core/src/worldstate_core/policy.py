"""Product policy boundaries for user-controlled model prompts."""

from __future__ import annotations

import re


class PromptPolicyError(ValueError):
    """Raised when prompts request an intentionally unsupported capability."""


_SENSITIVE_PATTERNS = (
    re.compile(r"\brace\b", re.IGNORECASE),
    re.compile(r"\bethnic(?:ity|ities)?\b", re.IGNORECASE),
    re.compile(r"\bnationality\b", re.IGNORECASE),
    re.compile(r"\breligion\b", re.IGNORECASE),
    re.compile(r"\bsexual orientation\b", re.IGNORECASE),
    re.compile(r"\bpolitical affiliation\b", re.IGNORECASE),
    re.compile(r"\bmedical (?:condition|status)\b", re.IGNORECASE),
)


def validate_object_prompts(prompts: tuple[str, ...], *, maximum: int = 32) -> tuple[str, ...]:
    """Normalize ordinary-object prompts and reject sensitive-trait inference."""

    if not prompts:
        raise PromptPolicyError("at least one object prompt is required")
    if len(prompts) > maximum:
        raise PromptPolicyError(f"no more than {maximum} prompts are allowed")

    normalized: list[str] = []
    for prompt in prompts:
        value = " ".join(prompt.split()).strip()
        if not value:
            raise PromptPolicyError("object prompts cannot be blank")
        if len(value) > 80:
            raise PromptPolicyError("object prompts cannot exceed 80 characters")
        if any(pattern.search(value) for pattern in _SENSITIVE_PATTERNS):
            raise PromptPolicyError(
                "WorldState supports ordinary-object perception, not sensitive-trait inference"
            )
        normalized.append(value)
    return tuple(dict.fromkeys(normalized))
