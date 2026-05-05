from __future__ import annotations

import errno

_DISCONNECT_ERRNO_SET = {
    errno.EPIPE,
    errno.ECONNRESET,
    errno.ECONNABORTED,
}


def is_client_disconnect_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    return getattr(exc, "errno", None) in _DISCONNECT_ERRNO_SET
