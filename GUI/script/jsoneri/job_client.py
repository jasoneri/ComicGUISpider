from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QHttpMultiPart, QHttpPart, QNetworkAccessManager, QNetworkReply, QNetworkRequest

from utils.script.jsoneri.imgpalace_job import (
    JobClientError,
    JobDraftMultipartPayload,
    build_commit_payload,
    build_job_draft_path,
    build_job_path,
    map_http_error,
    parse_commit_response,
    parse_create_response,
)

from .models import normalize_api_base_url


class _JobRequestFailure(RuntimeError):
    def __init__(self, error: JobClientError):
        super().__init__(error.message)
        self.error = error


class JsoneriImgPalaceJobClient(QObject):
    """Asynchronous transport for the imgPalace draft-and-commit job API."""

    draft_created = Signal(object, object)
    job_committed = Signal(object, object)
    job_failed = Signal(object, str, object)

    def __init__(self, *, base_url: str = "", token: str = "", parent=None, manager=None):
        super().__init__(parent)
        self._manager = manager or QNetworkAccessManager(self)
        self._base_url = ""
        self._token = ""
        self._reply_handlers: dict[int, object] = {}
        self.configure(base_url=base_url, token=token)

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._token)

    def configure(self, *, base_url: str, token: str) -> None:
        self._base_url = normalize_api_base_url(base_url)
        self._token = str(token or "").strip()

    def create_draft(self, *, draft: JobDraftMultipartPayload, request_id: object = None) -> None:
        multi_part = self._build_draft_multipart(draft)
        reply = self._manager.post(self._request(build_job_draft_path()), multi_part)
        multi_part.setParent(reply)
        handler = lambda reply=reply, request_id=request_id: self._handle_draft_reply(request_id, reply)
        self._reply_handlers[id(reply)] = handler
        reply.finished.connect(handler)

    def commit_draft(self, job_id: str, *, request_id: object = None) -> None:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            raise ValueError("job_id must be a non-empty string.")
        reply = self._manager.sendCustomRequest(
            self._request(build_job_path(normalized_job_id), json_body=True), b"PATCH",
            self._json_body(build_commit_payload()),
        )
        handler = lambda reply=reply, request_id=request_id: self._handle_commit_reply(request_id, reply)
        self._reply_handlers[id(reply)] = handler
        reply.finished.connect(handler)

    def _request(self, path: str, *, json_body: bool = False) -> QNetworkRequest:
        if not self.is_configured:
            raise RuntimeError("imgPalace job API URL and Bearer token must be configured before submitting a job.")
        request = QNetworkRequest(QUrl(f"{self._base_url}{path}"))
        if json_body:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Authorization", f"Bearer {self._token}".encode("utf-8"))
        return request

    @staticmethod
    def _json_body(payload: dict) -> QByteArray:
        return QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    @staticmethod
    def _build_draft_multipart(draft: JobDraftMultipartPayload) -> QHttpMultiPart:
        multi_part = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
        payload_part = QHttpPart()
        payload_part.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        payload_part.setHeader(QNetworkRequest.KnownHeaders.ContentDispositionHeader, 'form-data; name="payload"')
        payload_part.setBody(draft.payload_json)
        reference_part = QHttpPart()
        reference_part.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, draft.reference_content_type)
        reference_part.setHeader(
            QNetworkRequest.KnownHeaders.ContentDispositionHeader,
            f'form-data; name="reference"; filename="{draft.reference_filename}"',
        )
        reference_part.setBody(draft.reference)
        multi_part.append(payload_part)
        multi_part.append(reference_part)
        return multi_part

    def _handle_draft_reply(self, request_id: object, reply: QNetworkReply) -> None:
        try:
            result = self._read_create_result(reply)
        except _JobRequestFailure as error:
            self.job_failed.emit(request_id, "draft", error.error)
        except (TypeError, ValueError) as error:
            self.job_failed.emit(request_id, "draft", self._invalid_response_error(reply, error))
        else:
            self.draft_created.emit(request_id, result)
        finally:
            self._reply_handlers.pop(id(reply), None)
            reply.deleteLater()

    def _handle_commit_reply(self, request_id: object, reply: QNetworkReply) -> None:
        try:
            result = parse_commit_response(self._read_json_reply(reply))
        except _JobRequestFailure as error:
            self.job_failed.emit(request_id, "commit", error.error)
        except (TypeError, ValueError) as error:
            self.job_failed.emit(request_id, "commit", self._invalid_response_error(reply, error))
        else:
            self.job_committed.emit(request_id, result)
        finally:
            self._reply_handlers.pop(id(reply), None)
            reply.deleteLater()

    def _read_create_result(self, reply: QNetworkReply):
        return parse_create_response(self._read_json_reply(reply))

    def _read_json_reply(self, reply: QNetworkReply):
        data = self._read_reply_or_raise(reply)
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("imgPalace job API response must be valid JSON.") from error

    @staticmethod
    def _read_reply_or_raise(reply: QNetworkReply) -> bytes:
        data = bytes(reply.readAll())
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if reply.error() == QNetworkReply.NetworkError.NoError and (
            not isinstance(status, int) or 200 <= status < 300
        ):
            return data
        error = map_http_error(status if isinstance(status, int) else None, data)
        raise _JobRequestFailure(error)

    @staticmethod
    def _invalid_response_error(reply: QNetworkReply, error: Exception) -> JobClientError:
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        return map_http_error(status if isinstance(status, int) else None, str(error))
