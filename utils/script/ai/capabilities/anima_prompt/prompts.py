from __future__ import annotations

from utils.script.image.anima import anima_spec


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def build_messages(
    *,
    tag_context: str,
    nl_instruction: str,
    preset: str,
) -> list[dict[str, str]]:
    """Build the English instruction contract for one prompt merge."""
    context = _required_text(tag_context, "tag_context")
    instruction = _required_text(nl_instruction, "nl_instruction")
    selected_preset = _required_text(preset, "preset")
    format_rules = anima_spec.format_rules_text()
    system_prompt = f"""\
You merge a natural-language image instruction into an existing ANIMA prompt.
Return only a comma-separated tag prompt. Do not return Markdown, explanations, or
JSON.

The following format contract is authoritative and must be followed exactly:
{format_rules}

Tag-first policy:
- Keep every existing tag verbatim unless the user's instruction explicitly asks to
  replace or remove that tag.
- Preserve all content the user did not mention; never rewrite the whole prompt from
  general knowledge.
- Add only tags needed by the instruction.
- The selected preset is {selected_preset!r}; do not move its quality or safety tags.
"""
    user_prompt = f"""\
Existing ANIMA prompt:
---
{context}
---

User instruction:
---
{instruction}
---

Merge the instruction into the existing prompt and return the complete resulting
prompt only.
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
