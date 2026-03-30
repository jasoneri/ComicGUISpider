from __future__ import annotations

import asyncio
import threading
from contextlib import suppress
from typing import Optional

import dns.asyncresolver
import dns.flags
import dns.message
import dns.rcode
import dns.resolver
import dns.rdatatype
from loguru import logger

from .doh import (
    DNS_STUB_HOST,
    DNS_STUB_PORT,
    DOH_CONNECT_PROXY_HOST,
    create_async_doh_resolver,
    normalize_doh_url,
    resolve_host_via_doh,
)


class _DoHDnsProtocol(asyncio.DatagramProtocol):
    def __init__(self, doh_url: str):
        self._resolver = create_async_doh_resolver(doh_url)
        self._transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data: bytes, addr):
        asyncio.create_task(self._handle_query(data, addr))

    async def _handle_query(self, data: bytes, addr):
        try:
            request = dns.message.from_wire(data)
        except Exception:
            return

        response = dns.message.make_response(request)
        response.flags |= dns.flags.RA
        if not request.question:
            response.set_rcode(dns.rcode.FORMERR)
            self._send(response, addr)
            return

        question = request.question[0]
        if question.rdtype not in {dns.rdatatype.A, dns.rdatatype.AAAA}:
            response.set_rcode(dns.rcode.NOTIMP)
            self._send(response, addr)
            return

        try:
            answer = await self._resolver.resolve(
                question.name,
                question.rdtype,
                search=False,
                raise_on_no_answer=False,
            )
        except dns.resolver.NXDOMAIN:
            response.set_rcode(dns.rcode.NXDOMAIN)
        except Exception as exc:
            logger.warning(
                f"[SharedDoH] query failed qname={question.name} "
                f"rdtype={dns.rdatatype.to_text(question.rdtype)} error={exc}"
            )
            response.set_rcode(dns.rcode.SERVFAIL)
        else:
            if answer.rrset is not None:
                if answer.response and answer.response.answer:
                    response.answer.extend(answer.response.answer)
                else:
                    response.answer.append(answer.rrset)
        self._send(response, addr)

    def _send(self, response: dns.message.Message, addr):
        if self._transport is None:
            return
        try:
            self._transport.sendto(response.to_wire(), addr)
        except Exception:
            return


class _DoHDnsStubService:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_future: Optional[asyncio.Future] = None
        self._startup_error: Optional[BaseException] = None
        self._doh_url = ""

    def ensure_started(self, doh_url: str, *, timeout: float = 5.0) -> None:
        normalized_url = normalize_doh_url(doh_url)
        if not normalized_url:
            return
        with self._lock:
            if self._is_running_locked(normalized_url):
                return
            self._stop_locked()
            self._ready = threading.Event()
            self._startup_error = None
            self._doh_url = normalized_url
            self._thread = threading.Thread(
                target=self._thread_main,
                args=(normalized_url, self._ready),
                name="DoHDnsStub",
                daemon=True,
            )
            self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError("DoH DNS stub startup timed out")
        if self._startup_error is not None:
            raise RuntimeError(
                f"DoH DNS stub failed at {DNS_STUB_HOST}:{DNS_STUB_PORT}"
            ) from self._startup_error

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _is_running_locked(self, doh_url: str) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._startup_error is None
            and self._doh_url == doh_url
            and self._stop_future is not None
        )

    def _stop_locked(self) -> None:
        loop = self._loop
        stop_future = self._stop_future
        thread = self._thread
        self._loop = None
        self._stop_future = None
        self._thread = None
        self._doh_url = ""
        if loop is not None and stop_future is not None and not stop_future.done():
            try:
                loop.call_soon_threadsafe(stop_future.set_result, None)
            except RuntimeError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def _thread_main(self, doh_url: str, ready_event: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        transport: Optional[asyncio.DatagramTransport] = None
        stop_future = loop.create_future()
        try:
            protocol_factory = lambda: _DoHDnsProtocol(doh_url)
            transport, _protocol = loop.run_until_complete(
                loop.create_datagram_endpoint(
                    protocol_factory,
                    local_addr=(DNS_STUB_HOST, DNS_STUB_PORT),
                )
            )
            with self._lock:
                self._loop = loop
                self._stop_future = stop_future
            logger.info(
                f"[SharedDoH] started stub={DNS_STUB_HOST}:{DNS_STUB_PORT} doh={doh_url}"
            )
            ready_event.set()
            loop.run_until_complete(stop_future)
        except Exception as exc:
            self._startup_error = exc
            ready_event.set()
        finally:
            if transport is not None:
                transport.close()
                loop.run_until_complete(asyncio.sleep(0))
            loop.close()
            with self._lock:
                if self._loop is loop:
                    self._loop = None
                    self._stop_future = None


_doh_dns_stub_service = _DoHDnsStubService()


def ensure_doh_dns_stub_started(doh_url: str, *, timeout: float = 5.0) -> None:
    _doh_dns_stub_service.ensure_started(doh_url, timeout=timeout)


async def ensure_doh_dns_stub_started_async(doh_url: str, *, timeout: float = 5.0) -> None:
    await asyncio.to_thread(ensure_doh_dns_stub_started, doh_url, timeout=timeout)


def shutdown_doh_dns_stub() -> None:
    _doh_dns_stub_service.stop()


class _DoHConnectProxyService:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._stop_future: Optional[asyncio.Future] = None
        self._startup_error: Optional[BaseException] = None
        self._doh_url = ""
        self._proxy_port = 0

    def ensure_started(self, doh_url: str, *, timeout: float = 5.0) -> str:
        normalized_url = normalize_doh_url(doh_url)
        if not normalized_url:
            return ""
        with self._lock:
            if self._is_running_locked(normalized_url):
                return f"{DOH_CONNECT_PROXY_HOST}:{self._proxy_port}"
            self._stop_locked()
            self._ready = threading.Event()
            self._startup_error = None
            self._doh_url = normalized_url
            self._proxy_port = 0
            self._thread = threading.Thread(
                target=self._thread_main,
                args=(normalized_url, self._ready),
                name="DoHConnectProxy",
                daemon=True,
            )
            self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError("DoH CONNECT proxy startup timed out")
        if self._startup_error is not None:
            raise RuntimeError("DoH CONNECT proxy failed to start") from self._startup_error
        return f"{DOH_CONNECT_PROXY_HOST}:{self._proxy_port}"

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _is_running_locked(self, doh_url: str) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._startup_error is None
            and self._doh_url == doh_url
            and self._stop_future is not None
            and self._proxy_port > 0
        )

    def _stop_locked(self) -> None:
        loop = self._loop
        stop_future = self._stop_future
        thread = self._thread
        self._loop = None
        self._server = None
        self._stop_future = None
        self._thread = None
        self._proxy_port = 0
        self._doh_url = ""
        if loop is not None and stop_future is not None and not stop_future.done():
            try:
                loop.call_soon_threadsafe(stop_future.set_result, None)
            except RuntimeError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def _thread_main(self, doh_url: str, ready_event: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_future = loop.create_future()
        server: Optional[asyncio.AbstractServer] = None
        try:
            resolver = create_async_doh_resolver(doh_url)
            server = loop.run_until_complete(
                asyncio.start_server(
                    lambda reader, writer: self._handle_client(reader, writer, resolver),
                    DOH_CONNECT_PROXY_HOST,
                    0,
                )
            )
            sockets = server.sockets or []
            if not sockets:
                raise RuntimeError("DoH CONNECT proxy did not bind any sockets")
            self._proxy_port = int(sockets[0].getsockname()[1])
            with self._lock:
                self._loop = loop
                self._server = server
                self._stop_future = stop_future
            logger.info(
                f"[SharedDoH] started connect proxy={DOH_CONNECT_PROXY_HOST}:{self._proxy_port} doh={doh_url}"
            )
            ready_event.set()
            loop.run_until_complete(stop_future)
        except Exception as exc:
            self._startup_error = exc
            ready_event.set()
        finally:
            if server is not None:
                server.close()
                with suppress(Exception):
                    loop.run_until_complete(server.wait_closed())
            loop.close()
            with self._lock:
                if self._loop is loop:
                    self._loop = None
                    self._server = None
                    self._stop_future = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        resolver: dns.asyncresolver.Resolver,
    ) -> None:
        remote_writer: Optional[asyncio.StreamWriter] = None
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not request_line:
                return
            parts = request_line.decode("latin-1", errors="ignore").strip().split(" ", 2)
            if len(parts) != 3:
                await self._send_proxy_error(writer, 400, "Bad Request")
                return
            method, target, _version = parts
            while True:
                header_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not header_line or header_line in {b"\r\n", b"\n"}:
                    break
            if method.upper() != "CONNECT":
                await self._send_proxy_error(writer, 405, "CONNECT Only")
                return

            host, _, port_text = target.rpartition(":")
            if not host or not port_text.isdigit():
                await self._send_proxy_error(writer, 400, "Bad CONNECT Target")
                return
            target_host = await resolve_host_via_doh(resolver, host, timeout=5.0)
            remote_reader, remote_writer = await asyncio.open_connection(target_host, int(port_text))
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._relay_bidirectional(reader, writer, remote_reader, remote_writer)
        except Exception as exc:
            logger.warning(f"[SharedDoH] webengine proxy request failed error={exc}")
            with suppress(Exception):
                if not writer.is_closing():
                    await self._send_proxy_error(writer, 502, "Bad Gateway")
        finally:
            if remote_writer is not None:
                remote_writer.close()
                with suppress(Exception):
                    await remote_writer.wait_closed()
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def _relay_bidirectional(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        remote_reader: asyncio.StreamReader,
        remote_writer: asyncio.StreamWriter,
    ) -> None:
        async def pump(source: asyncio.StreamReader, destination: asyncio.StreamWriter):
            try:
                while True:
                    chunk = await source.read(65536)
                    if not chunk:
                        break
                    destination.write(chunk)
                    await destination.drain()
            except Exception:
                return
            finally:
                with suppress(Exception):
                    destination.close()

        tasks = [
            asyncio.create_task(pump(client_reader, remote_writer)),
            asyncio.create_task(pump(remote_reader, client_writer)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            with suppress(Exception):
                await task

    @staticmethod
    async def _send_proxy_error(writer: asyncio.StreamWriter, status_code: int, reason: str) -> None:
        payload = f"HTTP/1.1 {status_code} {reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
        writer.write(payload.encode("latin-1"))
        await writer.drain()


_doh_connect_proxy_service = _DoHConnectProxyService()


def ensure_doh_connect_proxy_started(doh_url: str, *, timeout: float = 5.0) -> str:
    return _doh_connect_proxy_service.ensure_started(doh_url, timeout=timeout)


def shutdown_doh_connect_proxy() -> None:
    _doh_connect_proxy_service.stop()


def ensure_doh_webengine_proxy_started(doh_url: str, *, timeout: float = 5.0) -> str:
    return ensure_doh_connect_proxy_started(doh_url, timeout=timeout)


def shutdown_doh_webengine_proxy() -> None:
    shutdown_doh_connect_proxy()
