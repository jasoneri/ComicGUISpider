from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class ServerSurface:
    name: str
    mount_path: str
    app: Any
    lifespan_factory: Callable | None = None
    call_log: Any | None = None

    def lifespan(self):
        if self.lifespan_factory is None:
            return _empty_lifespan()
        return self.lifespan_factory()


@asynccontextmanager
async def server_surface_lifespan(surfaces: tuple[ServerSurface, ...]):
    async with AsyncExitStack() as stack:
        for surface in surfaces:
            await stack.enter_async_context(surface.lifespan())
        yield


def mount_server_surfaces(app, surfaces: tuple[ServerSurface, ...]):
    for surface in surfaces:
        app.mount(surface.mount_path, surface.app, name=surface.name)


@asynccontextmanager
async def _empty_lifespan():
    yield

