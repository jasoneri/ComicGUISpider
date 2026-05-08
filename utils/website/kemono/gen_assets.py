from __future__ import annotations

import asyncio

import httpx

from assets import res
from utils import temp_p
from utils.website.kemono.db import build_kemono_db_from_creators_bytes


KEMONO_CREATORS_API_URL = "https://kemono.cr/api/v1/creators"
HEADERS = {
    "accept": "application/json",
    "accept-language": res.Vars.ua_accept_language,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "referer": "https://kemono.cr/",
}


def _build_data_client() -> httpx.AsyncClient:
    kwargs = {"headers": HEADERS, "http2": True, "follow_redirects": True}
    kwargs["proxy"] = "http://127.0.0.1:10809"
    return httpx.AsyncClient(**kwargs)


async def fetch_kemono_creators_payload(*, data_client: httpx.AsyncClient, timeout: float = 60) -> bytes:
    resp = await data_client.get(KEMONO_CREATORS_API_URL, timeout=timeout)
    resp.raise_for_status()
    return resp.content


async def generate_kemono_db():
    resolved_db_path = temp_p.joinpath("kemono.db")
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    with _build_data_client() as data_client:
        payload = await fetch_kemono_creators_payload(data_client=data_client)
    return await asyncio.to_thread(build_kemono_db_from_creators_bytes, resolved_db_path, payload)


def main():
    written = asyncio.run(generate_kemono_db())
    print(f"[DONE] kemono db rows affected {written}")


if __name__ == "__main__":
    main()
