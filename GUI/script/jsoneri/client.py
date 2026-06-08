from __future__ import annotations

import json
from urllib.parse import quote

from PySide6.QtCore import QByteArray, QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .models import StatusSnapshot, normalize_api_base_url, normalize_status_payload


class JsoneriServicesStatusApiClient(QObject):
    status_received = Signal(int, object)
    status_unreachable = Signal(int, str)
    route_received = Signal(str, object)
    route_failed = Signal(str, str)
    suspect_reported = Signal(str, str)
    suspect_failed = Signal(str, str, str)

    def __init__(self, *, base_url: str = "", token: str = "", parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._base_url = ""
        self._token = ""
        self._status_in_flight = False
        self.configure(base_url=base_url, token=token)

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    @property
    def status_in_flight(self) -> bool:
        return self._status_in_flight

    def configure(self, *, base_url: str, token: str) -> None:
        self._base_url = normalize_api_base_url(base_url)
        self._token = str(token or "").strip()

    def fetch_status(self, generation: int) -> bool:
        if not self._base_url:
            self.status_unreachable.emit(generation, "Jsoneri Server Status API URL is not configured.")
            return True
        if self._status_in_flight:
            return False
        self._status_in_flight = True
        reply = self._manager.get(self._request("/api/status"))
        reply.finished.connect(lambda reply=reply, generation=generation: self._handle_status_reply(generation, reply))
        return True

    def fetch_route(self, service_name: str) -> None:
        service = str(service_name or "").strip()
        if not service:
            raise ValueError("service_name must be a non-empty string.")
        if not self._base_url:
            self.route_failed.emit(service, "Jsoneri Server Status API URL is not configured.")
            return
        reply = self._manager.get(self._request(f"/api/route/{quote(service, safe='')}"))
        reply.finished.connect(lambda reply=reply, service=service: self._handle_route_reply(service, reply))

    def report_suspect(self, service_name: str, url: str) -> None:
        service = str(service_name or "").strip()
        target_url = str(url or "").strip()
        if not service:
            raise ValueError("service_name must be a non-empty string.")
        if not target_url:
            raise ValueError("url must be a non-empty string.")
        if not self._base_url:
            self.suspect_failed.emit(service, target_url, "Jsoneri Server Status API URL is not configured.")
            return
        payload = {"service": service, "url": target_url, "token": self._token}
        body = QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        reply = self._manager.post(self._request("/api/suspect", authorized=True), body)
        reply.finished.connect(
            lambda reply=reply, service=service, target_url=target_url: self._handle_suspect_reply(service, target_url, reply)
        )

    def _request(self, path: str, *, authorized: bool = False) -> QNetworkRequest:
        from PySide6.QtCore import QUrl

        request = QNetworkRequest(QUrl(f"{self._base_url}{path}"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        if authorized and self._token:
            request.setRawHeader(b"Authorization", f"Bearer {self._token}".encode("utf-8"))
        return request

    def _handle_status_reply(self, generation: int, reply: QNetworkReply) -> None:
        self._status_in_flight = False
        try:
            payload = self._read_json_reply(reply)
            snapshot: StatusSnapshot = normalize_status_payload(payload)
        except Exception as error:
            self.status_unreachable.emit(generation, str(error))
        else:
            self.status_received.emit(generation, snapshot)
        finally:
            reply.deleteLater()

    def _handle_route_reply(self, service: str, reply: QNetworkReply) -> None:
        try:
            payload = self._read_json_reply(reply)
            if not isinstance(payload, dict):
                raise TypeError("route response must be an object.")
            raw_url = payload.get("url")
            url = raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None
        except Exception as error:
            self.route_failed.emit(service, str(error))
        else:
            self.route_received.emit(service, url)
        finally:
            reply.deleteLater()

    def _handle_suspect_reply(self, service: str, url: str, reply: QNetworkReply) -> None:
        try:
            self._read_reply_or_raise(reply)
        except Exception as error:
            self.suspect_failed.emit(service, url, str(error))
        else:
            self.suspect_reported.emit(service, url)
        finally:
            reply.deleteLater()

    def _read_json_reply(self, reply: QNetworkReply):
        data = self._read_reply_or_raise(reply)
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Jsoneri Server Status API response must be valid JSON.") from error

    @staticmethod
    def _read_reply_or_raise(reply: QNetworkReply) -> bytes:
        data = bytes(reply.readAll())
        if reply.error() == QNetworkReply.NetworkError.NoError:
            return data
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status_label = f"HTTP {status}" if status else "network error"
        detail = data.decode("utf-8", errors="replace").strip() or reply.errorString()
        raise RuntimeError(f"Jsoneri Server Status API request failed: {status_label}: {detail}")
