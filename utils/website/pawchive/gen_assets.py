from __future__ import annotations

import asyncio
from copy import deepcopy

import httpx

from assets import res
from utils import temp_p
from utils.website.pawchive.db import build_pawchive_db_from_creators_bytes
from utils.website.pawchive import *


PAWCHIVE_CREATORS_API_URL = creators_txt
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


async def fetch_pawchive_creators_payload(*, data_client: httpx.AsyncClient, timeout: float = 60) -> bytes:
    resp = await data_client.get(PAWCHIVE_CREATORS_API_URL, timeout=timeout)
    resp.raise_for_status()
    return resp.content


async def generate_pawchive_db():
    resolved_db_path = temp_p.joinpath("pawchive.db")
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    async with _build_data_client() as data_client:
        payload = await fetch_pawchive_creators_payload(data_client=data_client)
    return await asyncio.to_thread(build_pawchive_db_from_creators_bytes, resolved_db_path, payload)


def main():
    written = asyncio.run(generate_pawchive_db())
    print(f"[DONE] pawchive db rows affected {written}")


if __name__ == "__main__":
    main()
