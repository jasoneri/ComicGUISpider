from __future__ import annotations

import asyncio
from copy import deepcopy

import httpx

from assets import res
from utils import temp_p
from utils.website.kemono.db import build_kemono_db_from_creators_bytes
from utils.website.kemono import *


KEMONO_CREATORS_API_URL = creators_txt
HEADERS = deepcopy(headers)
HEADERS.update({
    "accept": "application/json",
    "accept-language": res.Vars.ua_accept_language,
    "referer": f"https://{domain}",
})


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
    async with _build_data_client() as data_client:
        payload = await fetch_kemono_creators_payload(data_client=data_client)
    return await asyncio.to_thread(build_kemono_db_from_creators_bytes, resolved_db_path, payload)


def main():
    written = asyncio.run(generate_kemono_db())
    print(f"[DONE] kemono db rows affected {written}")


if __name__ == "__main__":
    main()
