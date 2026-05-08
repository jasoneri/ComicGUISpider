import argparse
import json
import random
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import httpx

from assets import res
from utils import conf, ori_path


API_URL = "https://nhentai.net/api/v2"
TAG_TYPES = [
    ("parody", 1),
    ("character", 2),
    ("tag", 3),
    ("artist", 4),
    ("group", 5),
    ("language", 6),
    ("category", 7),
]
TYPE_BY_CATEGORY = {category: name for name, category in TAG_TYPES}
HEADERS = {
    "accept": "application/json",
    "accept-language": res.Vars.ua_accept_language,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "referer": "https://nhentai.net/",
}


def _make_client(proxy_addr=None):
    kwargs = dict(http2=True, headers=HEADERS)
    if proxy_addr:
        kwargs["proxy"] = f"http://{proxy_addr}"
    return httpx.Client(**kwargs)


def _get_paths(db_path_override=None):
    if db_path_override:
        db_p = Path(db_path_override)
        db_p.parent.mkdir(parents=True, exist_ok=True)
        return db_p
    return ori_path.joinpath("__temp/nhentai.db")


def _get_proxy():
    return (conf.proxies or [None])[0]


def _default_seed_path():
    return ori_path.joinpath("test/analyze/nhentai/tags.json")


class Db:
    tags_tb = """
        CREATE TABLE IF NOT EXISTS `tags` (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            type TEXT NOT NULL,
            category INTEGER NOT NULL
        );
    """
    tags_type_idx = "CREATE INDEX IF NOT EXISTS `idx_tags_type` ON `tags` (`type`);"
    tags_name_idx = "CREATE INDEX IF NOT EXISTS `idx_tags_name` ON `tags` (`name`);"

    @classmethod
    def create_tables(cls, db_p):
        with closing(sqlite3.connect(db_p)) as db_conn:
            cursor = db_conn.cursor()
            cursor.execute(cls.tags_tb)
            cursor.execute(cls.tags_type_idx)
            cursor.execute(cls.tags_name_idx)
            db_conn.commit()


def _request_with_retry(client, url, max_retries=3, base_delay=2, jitter=1, timeout=10):
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url, timeout=timeout)
            if resp.status_code == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
                print(f"  [RATE_LIMIT] retry {attempt + 1}/{max_retries} after {delay:.1f}s")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException, json.JSONDecodeError) as exc:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
            print(f"  [RETRY] {attempt + 1}/{max_retries} after {delay:.1f}s - {exc}")
            time.sleep(delay)


def _normalize_seed_row(row):
    if not isinstance(row, list) or len(row) != 4:
        raise ValueError(f"invalid nhentai tag seed row: {row!r}")
    tag_id, name, count, category = row
    category = int(category)
    tag_type = TYPE_BY_CATEGORY.get(category)
    if tag_type is None:
        raise ValueError(f"invalid nhentai tag category: {category}")
    return int(tag_id), str(name), int(count), tag_type, category


def load_seed_tags(seed_path):
    seed_p = Path(seed_path)
    if not seed_p.exists():
        return []
    data = json.loads(seed_p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"nhentai tag seed root must be list: {seed_p}")
    return [_normalize_seed_row(row) for row in data]


def _normalize_api_row(row, tag_type, category):
    if not isinstance(row, dict):
        raise ValueError(f"invalid nhentai tag API row: {row!r}")
    return int(row["id"]), str(row["name"]), int(row["count"]), tag_type, category


def _scrape_type(client, tag_type, category, per_page=100, delay=2, timeout=10, max_retries=3):
    current_page = 1
    while True:
        print(f"Getting tags type '{tag_type}' page {current_page}")
        payload = _request_with_retry(
            client, f"{API_URL}/tags/{tag_type}?page={current_page}&per_page={per_page}", max_retries=max_retries, timeout=timeout,
        )
        results = payload.get("result")
        if not isinstance(results, list):
            raise ValueError(f"nhentai tags/{tag_type} page {current_page} missing result list")
        for row in results:
            yield _normalize_api_row(row, tag_type, category)
        num_pages = int(payload.get("num_pages") or 0)
        if current_page >= num_pages:
            break
        current_page += 1
        if delay:
            time.sleep(delay)


def _save_tags(db_conn, rows):
    with closing(db_conn.cursor()) as cursor:
        cursor.executemany(
            """
            INSERT INTO `tags` (id, name, count, type, category) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                count=excluded.count,
                type=excluded.type,
                category=excluded.category
            """,
            rows,
        )
        db_conn.commit()
        return cursor.rowcount


def seed_and_scrape(db_p, seed_path=None, skip_online=False, per_page=100, delay=2, timeout=10, max_retries=3):
    total_written = 0
    with closing(sqlite3.connect(db_p)) as db_conn:
        seed_rows = load_seed_tags(seed_path or _default_seed_path())
        if seed_rows:
            total_written += _save_tags(db_conn, seed_rows)
            print(f"[SEED] written {len(seed_rows)} rows")
        if skip_online:
            print(f"[DONE] seed only, sqlite rows affected {total_written}")
            return True

        client = _make_client(_get_proxy())
        failed = []
        for tag_type, category in TAG_TYPES:
            try:
                rows = list(
                    _scrape_type(client, tag_type, category, per_page=per_page, delay=delay, timeout=timeout, max_retries=max_retries)
                )
                total_written += _save_tags(db_conn, rows)
                print(f"[SUCCESS] {tag_type} written {len(rows)} rows")
            except Exception as exc:
                print(f"[ERROR] {tag_type} {exc}")
                failed.append(tag_type)
        print(f"\n{'=' * 40}\n[DONE] sqlite rows affected {total_written}, failed {len(failed)}")
        if failed:
            print(f"[FAILED] {failed}")
        return not failed


def main():
    parser = argparse.ArgumentParser(description="Scrape nhentai tag dataset into SQLite")
    parser.add_argument("--db-path", type=str, default=None, help="override nhentai.db path (for CI)")
    parser.add_argument(
        "--seed-json", type=str, default=None, help="seed JSON path, defaults to test/analyze/nhentai/tags.json when present"
    )
    parser.add_argument("--skip-online", action="store_true", help="only import seed JSON into SQLite")
    parser.add_argument("--per-page", type=int, default=100, help="API page size (default: 100)")
    parser.add_argument("--delay", type=float, default=2, help="delay between API pages in seconds (default: 2)")
    parser.add_argument("--max-retries", type=int, default=3, help="max retries per request (default: 3)")
    parser.add_argument("--timeout", type=int, default=10, help="request timeout in seconds (default: 10)")
    args = parser.parse_args()

    db_p = _get_paths(args.db_path)
    Db.create_tables(db_p)
    success = seed_and_scrape(
        db_p, seed_path=args.seed_json, skip_online=args.skip_online, per_page=args.per_page, delay=args.delay,
        max_retries=args.max_retries, timeout=args.timeout,
    )
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
