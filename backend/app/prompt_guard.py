"""Small check for obvious prompt-injection text in a custom transcript."""

from __future__ import annotations

import re

INJECTION = [
    re.compile(r"ignore (all )?(previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"disregard (all )?(previous|prior|above)", re.I),
    re.compile(r"you are now ", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"<(system|assistant)>", re.I),
    re.compile(r"reveal (your |the )?(system|hidden) (prompt|instructions)", re.I),
]


def prompt_injection_warning(text: str) -> str | None:
    if any(pattern.search(text) for pattern in INJECTION):
        return "This text looks like a prompt-injection attempt. Use a normal call transcript."
    return None
