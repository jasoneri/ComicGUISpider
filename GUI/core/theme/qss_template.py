from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from string import Template

_QSS_SECTION_RE = re.compile(
    r"/\*\s*@section\s+(?P<name>[\w.-]+)\s*\*/(?P<body>.*?)/\*\s*@endsection\s*\*/",
    re.DOTALL,
)
_QSS_TOKEN_RE = re.compile(
    r"/\*\s*@tokens\s+(?P<name>[\w.-]+)\s*\*/(?P<body>.*?)/\*\s*@endtokens\s*\*/",
    re.DOTALL,
)


def _parse_qss_tokens(body: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"Invalid QSS token line: {raw_line!r}")
        tokens[key.strip()] = value.strip().rstrip(";")
    return tokens


@lru_cache(maxsize=None)
def load_templated_qss_document(path_text: str) -> tuple[dict[str, Template], dict[str, dict[str, str]]]:
    path = Path(path_text)
    raw = path.read_text(encoding="utf-8")
    sections = {
        match.group("name"): Template(match.group("body").strip())
        for match in _QSS_SECTION_RE.finditer(raw)
    }
    token_sets = {
        match.group("name"): _parse_qss_tokens(match.group("body"))
        for match in _QSS_TOKEN_RE.finditer(raw)
    }
    if not sections:
        raise RuntimeError(f"No QSS sections found in {path}")
    if not token_sets:
        raise RuntimeError(f"No QSS token sets found in {path}")
    return sections, token_sets


def read_templated_qss_tokens(path: Path, theme_name: str) -> dict[str, str]:
    _, token_sets = load_templated_qss_document(str(path.resolve()))
    tokens = token_sets.get(theme_name)
    if tokens is None:
        raise KeyError(f"QSS token set is missing theme {theme_name!r}: {path}")
    return dict(tokens)


def render_templated_qss_section(path: Path, theme_name: str, section_name: str, **overrides: str) -> str:
    sections, _ = load_templated_qss_document(str(path.resolve()))
    template = sections.get(section_name)
    if template is None:
        raise KeyError(f"QSS section is missing {section_name!r}: {path}")
    tokens = read_templated_qss_tokens(path, theme_name)
    tokens.update({key: str(value) for key, value in overrides.items()})
    return template.substitute(tokens).strip()
