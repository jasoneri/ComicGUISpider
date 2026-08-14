from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from utils.script.image.danbooru.models import DanbooruPost

API_VERSION = "imgpalace.job.v1"
SERVICE_NAME_DEFAULT = "raw-image"
JOB_DRAFTS_PATH = "/api/jobs/drafts"
JOB_REFERENCE_FIELD = "reference"
JOB_PAYLOAD_FIELD = "payload"
# Job action registry. UI surfaces (e.g. TagExport ComboBox) MUST load choices from
# ``iter_action_preset_names`` / ``action_preset`` — never hardcode parallel option lists.
# Add a real product action by registering here (name + params), not by inventing empty stubs.
DEFAULT_ACTION_NAME = "img2img"
DEFAULT_ACTION: dict[str, Any] = {
    "action": DEFAULT_ACTION_NAME,
    "params": {"strength": 0.75},
}

_ACTION_PRESETS: dict[str, dict[str, Any]] = {
    DEFAULT_ACTION_NAME: {
        "action": DEFAULT_ACTION_NAME,
        "params": dict(DEFAULT_ACTION["params"]),
    },
}


@dataclass(frozen=True, slots=True)
class JobCreateResult:
    job_id: str
    status: str
    progress_url: str
    self_url: str


@dataclass(frozen=True, slots=True)
class JobDraftMultipartPayload:
    """Transport-neutral parts for one multipart draft creation request."""

    payload_json: bytes
    reference: bytes
    reference_filename: str
    reference_content_type: str


@dataclass(frozen=True, slots=True)
class JobClientError:
    code: str
    message: str
    retryable: bool
    http_status: int | None = None


def iter_action_preset_names() -> tuple[str, ...]:
    """Stable ordered names for ComboBox / pickers that bind to job ``action``."""
    return tuple(_ACTION_PRESETS.keys())


def register_action_preset(
    name: str,
    *,
    action: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> None:
    """Extend the registry when a real product action is ready (params required for the job type)."""
    key = str(name or "").strip()
    if not key:
        raise ValueError("action preset name must be non-empty.")
    action_name = str(action or key).strip()
    if not action_name:
        raise ValueError("action preset action field must be non-empty.")
    _ACTION_PRESETS[key] = {
        "action": action_name,
        "params": dict(params or {}),
    }


def action_preset(name: str) -> dict[str, Any]:
    key = str(name or "").strip() or DEFAULT_ACTION_NAME
    preset = _ACTION_PRESETS.get(key)
    if preset is None:
        raise ValueError(f"Unsupported imgPalace action preset: {key!r}.")
    return {
        "action": preset["action"],
        "params": dict(preset.get("params") or {}),
    }


def build_source_meta(
    post: DanbooruPost,
    tags_prompt: object,
    *,
    identity: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build source metadata; ``tags_prompt`` is the already-selected visual prompt body."""
    prompt = _require_non_empty_string(tags_prompt, "tags_prompt")
    payload: dict[str, Any] = {
        "app": "cgs",
        "module": "danbooru",
        "post_id": int(post.post_id),
        "md5": str(post.md5 or ""),
        "tags": prompt,
        "source_urls": {
            "file": str(post.file_url or ""),
            "large": str(post.large_file_url or ""),
            "preview": str(post.preview_file_url or ""),
        },
    }
    if identity:
        payload["identity"] = _normalize_identity(identity)
    return payload


def build_client_meta(*, version: str = "") -> dict[str, str]:
    return {
        "name": "ComicGUISpider",
        "version": str(version or ""),
    }


def build_job_draft_path() -> str:
    return JOB_DRAFTS_PATH


def build_job_path(job_id: object) -> str:
    return f"/api/jobs/{quote(_require_non_empty_string(job_id, 'job_id'), safe='')}"


def build_job_confirm_path(job_id: object) -> str:
    return f"{build_job_path(job_id)}/confirm"


def build_draft_payload(
    post: DanbooruPost,
    tags_prompt: object,
    *,
    action: Mapping[str, Any],
    identity: Mapping[str, list[str]] | None = None,
    client_version: object = "",
) -> dict[str, Any]:
    """Build the JSON part of ``POST /api/jobs/drafts``.

    Selection and tag-group classification deliberately happen before this boundary.
    The client must pass only the General (+ opted-in Meta) prompt body as ``tags_prompt``.
    """
    prompt = _require_non_empty_string(tags_prompt, "tags_prompt")
    return {
        "api_version": API_VERSION,
        "source": build_source_meta(post, prompt, identity=identity),
        "action": _normalize_action(action),
        "client": build_client_meta(version=str(client_version or "")),
    }


def build_draft_multipart_payload(
    post: DanbooruPost,
    tags_prompt: object,
    *,
    action: Mapping[str, Any],
    reference: bytes,
    reference_filename: object,
    reference_content_type: object,
    identity: Mapping[str, list[str]] | None = None,
    client_version: object = "",
) -> JobDraftMultipartPayload:
    """Build transport-neutral multipart parts for a job draft.

    The Qt client owns QHttpMultiPart construction.  This value object gives it the
    exact JSON and binary parts without importing Qt into the pure utility layer.
    """
    if not isinstance(reference, bytes) or not reference:
        raise TypeError("reference must be non-empty bytes.")
    filename = _require_non_empty_string(reference_filename, "reference_filename")
    content_type = _require_non_empty_string(reference_content_type, "reference_content_type")
    payload = build_draft_payload(
        post,
        tags_prompt,
        action=action,
        identity=identity,
        client_version=client_version,
    )
    return JobDraftMultipartPayload(
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        reference=reference,
        reference_filename=filename,
        reference_content_type=content_type,
    )


def build_commit_payload() -> dict[str, str]:
    """Build the body for canonical ``PATCH /api/jobs/{job_id}`` commit."""
    return {"api_version": API_VERSION, "state": "committed"}


def build_confirm_payload() -> dict[str, str]:
    """Build the body for the documented compatibility ``POST .../confirm`` commit."""
    return build_commit_payload()


def parse_create_response(payload: Any) -> JobCreateResult:
    return _parse_job_response(payload, response_name="draft creation response")


def parse_commit_response(payload: Any) -> JobCreateResult:
    return _parse_job_response(payload, response_name="job commit response")


def _parse_job_response(payload: Any, *, response_name: str) -> JobCreateResult:
    if not isinstance(payload, Mapping):
        raise TypeError(f"imgPalace {response_name} must be an object.")
    api_version = _require_non_empty_string(payload.get("api_version"), "api_version")
    if api_version != API_VERSION:
        raise ValueError(f"api_version must be {API_VERSION!r}, got {api_version!r}.")
    job_id = _require_non_empty_string(payload.get("job_id"), "job_id")
    status = _require_non_empty_string(payload.get("status"), "status")
    links = payload.get("links")
    if not isinstance(links, Mapping):
        raise TypeError(f"imgPalace {response_name} links must be an object.")
    progress_url = _require_non_empty_string(links.get("progress"), "links.progress")
    self_url = _require_non_empty_string(links.get("self"), "links.self")
    return JobCreateResult(
        job_id=job_id,
        status=status,
        progress_url=progress_url,
        self_url=self_url,
    )


def map_http_error(status: int | None, body: bytes | Mapping[str, Any] | str | None) -> JobClientError:
    envelope = _error_envelope(body)
    code = str(envelope.get("code") or "").strip()
    message = str(envelope.get("message") or "").strip()
    retryable_raw = envelope.get("retryable")
    retryable = _optional_bool(retryable_raw, "retryable")
    if status == 401:
        return JobClientError(
            code=code or "unauthorized",
            message=message or "鉴权失败，请检查 jsoneriPalaces token",
            retryable=False,
            http_status=status,
        )
    if status in (402, 403):
        return JobClientError(
            code=code or "quota_exceeded",
            message=message or "额度不足",
            retryable=False,
            http_status=status,
        )
    if status == 429:
        return JobClientError(
            code=code or "rate_limited",
            message=message or "请求过频，稍后重试",
            retryable=True if retryable is None else retryable,
            http_status=status,
        )
    if status is not None and status >= 500:
        return JobClientError(
            code=code or "service_unavailable",
            message=message or "服务错误",
            retryable=True if retryable is None else retryable,
            http_status=status,
        )
    if status is None:
        return JobClientError(
            code=code or "service_unavailable",
            message=message or "服务暂不可用",
            retryable=True if retryable is None else retryable,
            http_status=None,
        )
    return JobClientError(
        code=code or "validation_error",
        message=message or f"请求失败 (HTTP {status})",
        retryable=retryable if retryable is not None else False,
        http_status=status,
    )


def toast_text(error: JobClientError) -> str:
    return str(error.message or error.code or "请求失败")


def _error_envelope(body: bytes | Mapping[str, Any] | str | None) -> dict[str, Any]:
    if body is None:
        return {}
    if isinstance(body, Mapping):
        nested = body.get("error")
        if isinstance(nested, Mapping):
            return dict(nested)
        return dict(body)
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace").strip()
    else:
        text = str(body).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}
    if isinstance(parsed, Mapping):
        nested = parsed.get("error")
        if isinstance(nested, Mapping):
            return dict(nested)
        return dict(parsed)
    return {"message": text}


def _normalize_action(action: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        raise TypeError("action must be an object.")
    action_name = _require_non_empty_string(action.get("action"), "action.action")
    if action_name not in _ACTION_PRESETS:
        raise ValueError(f"Unsupported imgPalace action: {action_name!r}.")
    params = action.get("params")
    if not isinstance(params, Mapping):
        raise TypeError("action.params must be an object.")
    return {"action": action_name, "params": dict(params)}


def _normalize_identity(identity: Mapping[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(identity, Mapping):
        raise TypeError("identity must be an object.")
    valid_keys = {"character", "artist", "copyright"}
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_tags in identity.items():
        key = _require_non_empty_string(raw_key, "identity key")
        if key not in valid_keys:
            raise ValueError(f"Unsupported identity group: {key!r}.")
        if not isinstance(raw_tags, list) or not raw_tags:
            raise TypeError(f"identity.{key} must be a non-empty array of strings.")
        tags = [_require_non_empty_string(tag, f"identity.{key} tag") for tag in raw_tags]
        normalized[key] = tags
    return normalized


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean when present.")
    return value
