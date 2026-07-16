from __future__ import annotations

import json

from utils.script.ai.kernel import extract_json_object

from .serp import SearchHit, parse_tag_query

LANGUAGE_LABELS = {
    "zh": "中文（含简体与繁体）",
    "ja": "日本語",
}

# Grounded extraction only: selection rules + schema.
# Do NOT embed domain gold answers / eval cases (contamination).
# Double braces are literal JSON for str.format.
_SYSTEM_PROMPT = """\
You are an evidence-only extractor for localized display names of Danbooru-style character tags.
Target language: {language_label}.

## Grounding (hard constraints)
- Use ONLY the evidence arrays in the user JSON (title/href/body/source).
- Treat parametric / pretrained knowledge as untrusted. If evidence and memory conflict, evidence wins.
- If evidence is missing, contradictory, or does not support a name in the target language, abstain: translated="" and confidence="unknown". Never invent or "fill" names.
- Never rewrite origin tags; they are immutable search keys.

## What counts as the target language (critical)
### When target is Chinese (中文)
- Chinese includes **both Simplified and Traditional** orthography. Do not reject Traditional forms.
- A candidate made of **Han / CJK ideographs** (汉字), including shared Sino-Japanese kanji forms found in wiki aliases, **is a valid Chinese display name**.
- Do **not** abstain only because the same string also appears on Japanese sites or is labeled Japanese in your prior knowledge.
- Prefer Simplified when both Simplified and Traditional forms appear in evidence; if only Traditional / shared-Han form appears, **use it** (confidence high/medium as appropriate).
- Treat as **not Chinese** (skip or lower rank) only when the candidate is primarily **kana** (hiragana/katakana), Latin-only, or a kana-heavy hybrid with no usable Han personal name.
- Parenthetical notes in Chinese/shared Han (e.g. costume labels using Han) are fine.

### When target is Japanese (日本語)
- Prefer candidates with kana and/or Japanese orthography present in evidence.
- Pure Han-only forms may still be used if they appear in evidence and no better Japanese form exists.

## Evidence priority (highest first)
1. source contains other_names or other_name (wiki alias lists)
2. source contains body (wiki prose, full-name lines, costume notes)
3. source contains link (wiki dtext labels)
4. anilist (native / full / alternative)
5. moegirl / SERP titles and snippets

## Selection procedure (apply per origin)
1. Collect candidate strings that appear in evidence (aliases, titles, quoted names, parenthetical localized forms). Do not add candidates that are not present.
2. Filter/rank by the target-language rules above. Prefer target-language candidates when available.
3. Prefer the most complete personal name over a shorter given-name-only fragment when both appear in evidence.
4. If tag_parts.costume is non-null, the display name must preserve that variant:
   - Prefer an evidence candidate that already includes the variant (parentheses or equivalent).
   - If evidence contains the base localized personal name (including source translate_map:parent) but no combined costume form, you MUST compose: base_from_evidence + structural costume from tag_parts.costume (the costume token is part of the origin tag structure, not parametric invention). Use a light parenthetical form such as base(costume) when no better costume gloss appears in evidence.
   - Do not invent a Chinese costume gloss (e.g. do not invent 泳装) unless that exact gloss appears in evidence; using the raw costume token from tag_parts is allowed.
5. Light punctuation normalization only (half/full-width parentheses, spacing). Do not change characters that appear in the chosen evidence span. Do not convert Traditional↔Simplified unless both forms already appear in evidence and you pick one of them.
6. Assign confidence: high = direct target-language alias or clear full-name line; medium = composed from multiple evidence fields or shared-Han form used for Chinese; low = weak single snippet; unknown = abstain.

## Output
Return JSON only, no markdown fences, no prose outside JSON:
{{"items":[{{"origin":"<echo input origin>","translated":"<display name or empty>","confidence":"high|medium|low|unknown"}}]}}
Every input origin appears exactly once. Order may match input order.
"""

_USER_PROMPT = """\
Task: for each tag, select a target-language display name using ONLY its evidence list.
Follow the system selection procedure and the target-language script rules.
For Chinese targets: Simplified and Traditional both count; shared Han names in evidence are valid — do not abstain just because they also look Japanese.
Abstain only when no suitable target-language candidate exists in evidence.
Input JSON:
{payload_json}
"""


def build_messages(
    *,
    language: str,
    batch: list[tuple[str, list[SearchHit]]],
) -> list[dict[str, str]]:
    language_label = LANGUAGE_LABELS.get(language, LANGUAGE_LABELS["zh"])
    if not batch:
        raise ValueError("build_messages requires non-empty batch")
    for origin, hits in batch:
        if not hits:
            raise ValueError(f"build_messages refuses empty evidence for origin={origin!r}")

    system_prompt = _SYSTEM_PROMPT.format(language_label=language_label)
    payload_items = []
    for origin, hits in batch:
        parts = parse_tag_query(origin)
        payload_items.append(
            {
                "origin": origin,
                "tag_parts": {
                    "base_name": parts.base_name,
                    "costume": parts.costume,
                    "series": parts.series,
                    "parent_tag": parts.parent_tag,
                    "series_tag": parts.series_tag,
                },
                "evidence": [
                    {
                        "title": hit.title,
                        "href": hit.href,
                        "body": hit.body,
                        "source": getattr(hit, "source", "") or "",
                    }
                    for hit in hits[:12]
                ],
            }
        )
    user_prompt = _USER_PROMPT.format(
        payload_json=json.dumps({"tags": payload_items}, ensure_ascii=False, indent=2)
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_translation_items(content: str) -> dict[str, str]:
    payload = extract_json_object(content)
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("json missing items list")
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        origin = " ".join(str(item.get("origin") or "").split())
        translated = " ".join(str(item.get("translated") or "").split())
        if not origin or not translated:
            continue
        result[origin] = translated
    return result
