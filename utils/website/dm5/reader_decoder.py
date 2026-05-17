from __future__ import annotations

import ast
import re


class Dm5ReaderDecoder:
    _packer_juicers = (
        r"}\s*\(\s*'(.*?)'\s*,\s*(\d+|\[\])\s*,\s*(\d+)\s*,\s*'(.*?)'\.split\('\|'\)(?:\s*,\s*(\d+)\s*,\s*(.*?))?\s*\)\s*\)",
        r'}\s*\(\s*"(.*?)"\s*,\s*(\d+|\[\])\s*,\s*(\d+)\s*,\s*"(.*?)"\.split\("\|"\)(?:\s*,\s*(\d+)\s*,\s*(.*?))?\s*\)\s*\)',
    )

    @staticmethod
    def _decode_js_string_literal(raw: str) -> str:
        normalized = str(raw or "").strip()
        if len(normalized) < 2 or normalized[0] not in {'"', "'"} or normalized[-1] != normalized[0]:
            raise ValueError(f"dm5 reader invalid js string literal: {raw!r}")
        body = normalized[1:-1]
        cooked: list[str] = []
        index = 0
        while index < len(body):
            if body[index] != "\\" or index + 1 >= len(body):
                cooked.append(body[index])
                index += 1
                continue
            marker = body[index + 1]
            if marker == "/":
                cooked.append("/")
                index += 2
                continue
            if marker == "\n":
                index += 2
                continue
            if marker == "\r":
                index += 2
                if index < len(body) and body[index] == "\n":
                    index += 1
                continue
            cooked.append(body[index])
            cooked.append(marker)
            index += 2
        try:
            value = ast.literal_eval(f"{normalized[0]}{''.join(cooked)}{normalized[0]}")
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"dm5 reader invalid js string literal: {raw!r}") from exc
        if not isinstance(value, str):
            raise ValueError(f"dm5 reader invalid js string literal: {raw!r}")
        return value

    @staticmethod
    def _consume_ws(script_text: str, index: int) -> int:
        while index < len(script_text) and script_text[index].isspace():
            index += 1
        return index

    @classmethod
    def _parse_js_string_at(cls, script_text: str, index: int) -> tuple[str, int]:
        index = cls._consume_ws(script_text, index)
        if index >= len(script_text) or script_text[index] not in {'"', "'"}:
            raise ValueError(f"dm5 reader invalid js string start: index={index}")
        quote = script_text[index]
        end = index + 1
        while end < len(script_text):
            char = script_text[end]
            if char == "\\":
                end += 2
                continue
            if char == quote:
                return script_text[index : end + 1], end + 1
            end += 1
        raise ValueError("dm5 reader unterminated js string literal")

    @classmethod
    def _iter_js_string_literals(cls, script_text: str):
        index = 0
        while index < len(script_text):
            if script_text[index] in {'"', "'"}:
                raw, next_index = cls._parse_js_string_at(script_text, index)
                yield raw
                index = next_index
                continue
            index += 1

    @classmethod
    def _parse_js_int_at(cls, script_text: str, index: int) -> tuple[int, int]:
        index = cls._consume_ws(script_text, index)
        end = index
        while end < len(script_text) and script_text[end].isdigit():
            end += 1
        if end == index:
            raise ValueError(f"dm5 reader invalid js int start: index={index}")
        return int(script_text[index:end]), end

    @classmethod
    def _parse_bracket_block(
        cls,
        script_text: str,
        index: int,
        *,
        open_char: str = "[",
        close_char: str = "]",
    ) -> tuple[str, int]:
        index = cls._consume_ws(script_text, index)
        if index >= len(script_text) or script_text[index] != open_char:
            raise ValueError(f"dm5 reader invalid bracket block start: index={index}")
        depth = 1
        end = index + 1
        while end < len(script_text):
            char = script_text[end]
            if char in {'"', "'"}:
                _, end = cls._parse_js_string_at(script_text, end)
                continue
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return script_text[index + 1 : end], end + 1
            end += 1
        raise ValueError("dm5 reader unterminated bracket block")

    @classmethod
    def _find_decl_assignment_index(cls, script_text: str, name: str) -> int:
        for prefix in ("var ", "let ", "const "):
            marker = f"{prefix}{name}"
            start = script_text.find(marker)
            if start == -1:
                continue
            assign = script_text.find("=", start + len(marker))
            if assign == -1:
                continue
            return assign + 1
        raise ValueError(f"dm5 reader missing {name}")

    @classmethod
    def _extract_decl_int(cls, script_text: str, name: str, *, request_url: str) -> int:
        try:
            value, _ = cls._parse_js_int_at(script_text, cls._find_decl_assignment_index(script_text, name))
            return value
        except ValueError as exc:
            raise ValueError(f"dm5 reader missing {name}: url={request_url}") from exc

    @classmethod
    def _extract_decl_string(cls, script_text: str, name: str, *, request_url: str) -> str:
        try:
            raw, _ = cls._parse_js_string_at(script_text, cls._find_decl_assignment_index(script_text, name))
            return cls._decode_js_string_literal(raw)
        except ValueError as exc:
            raise ValueError(f"dm5 reader missing {name}: url={request_url}") from exc

    @classmethod
    def _extract_decl_string_list(cls, script_text: str, name: str, *, request_url: str) -> list[str]:
        try:
            body, _ = cls._parse_bracket_block(script_text, cls._find_decl_assignment_index(script_text, name))
        except ValueError as exc:
            raise ValueError(f"dm5 reader missing {name}: url={request_url}") from exc
        return [cls._decode_js_string_literal(raw) for raw in cls._iter_js_string_literals(body)]

    @classmethod
    def _extract_suffix(cls, script_text: str, *, request_url: str) -> str:
        search_from = 0
        while True:
            start = script_text.find("pvalue[", search_from)
            if start == -1:
                break
            end = script_text.find(";", start)
            if end == -1:
                end = len(script_text)
            statement = script_text[start:end]
            if "=" not in statement or "pix" not in statement or "+" not in statement:
                search_from = start + 1
                continue
            literals = [cls._decode_js_string_literal(raw) for raw in cls._iter_js_string_literals(statement)]
            if literals:
                return literals[-1]
            search_from = start + 1
        raise ValueError(f"dm5 reader missing suffix: url={request_url}")

    @staticmethod
    def _extract_page_number(path: str, *, request_url: str) -> int:
        segment = str(path or "").rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
        if "_" not in segment:
            raise ValueError(f"dm5 reader bad page path: {path!r} url={request_url}")
        page_text = segment.split("_", 1)[0]
        if not page_text.isdigit():
            matched = re.search(r"-(\d+)$", page_text)
            if matched is None:
                raise ValueError(f"dm5 reader bad page path: {path!r} url={request_url}")
            return int(matched.group(1)) + 1
        return int(page_text)

    @classmethod
    def _encode_unpack_token(cls, index: int, radix: int) -> str:
        if index == 0:
            return "0"
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        token = ""
        while index:
            index, remainder = divmod(index, radix)
            token = (chr(remainder + 29) if remainder > 35 else chars[remainder]) + token
        return token

    @classmethod
    def _parse_packer_args(cls, script_text: str) -> tuple[str, int, int, list[str]] | None:
        normalized = str(script_text or "").replace("\\\\'", "\\'")
        for pattern in cls._packer_juicers:
            matched = re.search(pattern, normalized, re.DOTALL)
            if matched is None:
                continue
            payload, radix, count, dictionary = matched.group(1), matched.group(2), matched.group(3), matched.group(4)
            payload = payload.replace("\\\\", "\\").replace("\\'", "'")
            radix_value = 62 if radix == "[]" else int(radix)
            return payload, radix_value, int(count), dictionary.split("|")
        return None

    @classmethod
    def _unpack_packer(cls, script_text: str, *, request_url: str) -> str:
        parsed = cls._parse_packer_args(script_text)
        if parsed is None:
            raise ValueError(f"dm5 chapterfun response missing packed eval payload: url={request_url}")
        payload, radix, count, dictionary = parsed
        if count != len(dictionary):
            raise ValueError(
                f"dm5 chapterfun packed symtab mismatch: count={count} symtab_len={len(dictionary)} url={request_url}"
            )
        replacements = {
            cls._encode_unpack_token(index, radix): value for index, value in enumerate(dictionary) if value
        }
        return re.sub(
            r"\b\w+\b",
            lambda matched: replacements.get(matched.group(0), matched.group(0)),
            payload,
            flags=re.ASCII,
        )

    @classmethod
    def decode_page_urls(
        cls,
        script_text: str,
        *,
        request_url: str,
        expected_cid: str | None = None,
    ) -> list[tuple[int, str]]:
        if cls._parse_packer_args(script_text):
            unpacked = cls._unpack_packer(script_text, request_url=request_url)
        elif "dm5imagefun" in script_text and "pvalue" in script_text:
            unpacked = script_text
        else:
            raise ValueError(f"dm5 chapterfun response missing packed eval payload: url={request_url}")

        cid = str(cls._extract_decl_int(unpacked, "cid", request_url=request_url))
        if expected_cid is not None and str(expected_cid) != cid:
            raise ValueError(f"dm5 reader cid mismatch: expected={expected_cid} actual={cid} url={request_url}")

        pix = cls._extract_decl_string(unpacked, "pix", request_url=request_url)
        paths = cls._extract_decl_string_list(unpacked, "pvalue", request_url=request_url)
        if not paths:
            raise ValueError(f"dm5 reader empty pvalue: url={request_url}")

        suffix = cls._extract_suffix(unpacked, request_url=request_url)
        return [
            (cls._extract_page_number(path, request_url=request_url), f"{pix}{path}{suffix}")
            for path in paths
        ]
