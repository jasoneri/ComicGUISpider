import re
import json
import time
import random
import sqlite3
import argparse
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from lxml import html
from assets import res
from utils import temp_p


BASE_URL = "https://hitomi.la/all{category}-{letter}.html"
CATEGORIES = ['tags', 'artists', 'series', 'characters']
LETTERS = [*[chr(i) for i in range(97, 123)], '123']
HEADERS = {
    "accept": "*/*",
    "accept-language": res.Vars.ua_accept_language,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
    "referer": "https://hitomi.la/"
}
count_regex = re.compile(r'\((\d+)\)\s*$')
convention_tag_regex = re.compile(r'c\d+\Z', re.IGNORECASE)


def lstrip(text):
    if text.startswith("all"):
        return text[3:]
    return text


def _iter_category_letter_pairs():
    for category in CATEGORIES:
        for letter in LETTERS:
            yield category, letter


class Db:
    data_tb = """
        CREATE TABLE IF NOT EXISTS `%s` (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL UNIQUE,
            num INTEGER NOT NULL DEFAULT 1
            );
    """
    language_tb = """
        CREATE TABLE IF NOT EXISTS `language` (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL UNIQUE
            );
    """
    
    @classmethod
    def create_tables(cls, db_p):
        with closing(sqlite3.connect(db_p)) as db_conn:
            cursor = db_conn.cursor()
            for category, letter in _iter_category_letter_pairs():
                table_name = f"all{lstrip(category)}-{letter}"
                cursor.execute(cls.data_tb % table_name)
            cursor.execute(cls.language_tb)
            db_conn.commit()


def _request_with_retry(client, url, max_retries=3, base_delay=2, jitter=1, timeout=10):
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
            print(f"  [RETRY] {attempt+1}/{max_retries} after {delay:.1f}s - {e}")
            time.sleep(delay)


def _parse_post_item(li, category):
    def _normalize_content(content):
        content = content.strip()
        if category == "tags" and convention_tag_regex.fullmatch(content):
            return content.upper()
        return content
    content = _normalize_content(li.xpath("normalize-space(string(./a))"))
    if not content:
        return None
    count_match = count_regex.search(li.xpath("normalize-space(string(.))"))
    if count_match is None:
        href = li.xpath("./a/@href")
        raise ValueError(f"missing trailing count in hitomi list item: {href[0] if href else content!r}")
    return content, int(count_match.group(1))


def _parse_posts_page(page_text, category):
    tree = html.fromstring(page_text)
    items = []
    for li in tree.xpath('//ul[@class="posts"]/li'):
        item = _parse_post_item(li, category)
        if item is not None:
            items.append(item)
    return items


def _scrape_one(client, category, letter, timeout=10, max_retries=3):
    url = BASE_URL.format(category=category, letter=letter)
    page_text = _request_with_retry(client, url, max_retries=max_retries, timeout=timeout)
    return _parse_posts_page(page_text, category)


def _save_one(db_conn, table_name, items, rewrite_flag):
    if rewrite_flag:
        cursor = db_conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        cursor.execute(Db.data_tb % table_name)
        db_conn.commit()
    with closing(db_conn.cursor()) as cursor:
        cursor.executemany(f"INSERT OR IGNORE INTO `{table_name}` (content,num) VALUES (?,?)", items)
        db_conn.commit()
        print(f"[SUCCESS] {table_name} written {cursor.rowcount}")


def scrape_and_save(db_p, workers=2, max_retries=3, timeout=10):
    client = httpx.Client(
        http2=True, headers=HEADERS,
        # proxy="http://127.0.0.1:10809"
    )
    init_err_f = temp_p.joinpath('hitomi_db_init_err.json')
    tb_rewrite_flag = False
    tasks = []

    if init_err_f.exists():
        with open(init_err_f, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        if tasks:
            tb_rewrite_flag = True

    if not tasks:
        tasks = [f'{category}-{letter}' for category, letter in _iter_category_letter_pairs()]

    err = []

    def fetch_task(task_key):
        category, letter = task_key.split('-')
        category = lstrip(category)
        items = _scrape_one(client, category, letter, timeout=timeout, max_retries=max_retries)
        return task_key, f"all{category}-{letter}", items

    # fetch concurrently, write sequentially
    with closing(sqlite3.connect(db_p)) as db_conn:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_task, t): t for t in tasks}
            for future in as_completed(futures):
                task_key = futures[future]
                try:
                    _, table_name, items = future.result()
                    _save_one(db_conn, table_name, items, tb_rewrite_flag)
                except Exception as e:
                    print(f"[ERROR] {task_key} {e}")
                    err.append(task_key)

    with open(init_err_f, 'w', encoding='utf-8') as f:
        json.dump(err, f, ensure_ascii=False, indent=4)

    total = len(tasks)
    ok = total - len(err)
    print(f"\n{'='*40}\n[DONE] {ok}/{total} succeeded, {len(err)} failed")
    if err:
        print(f"[FAILED] {err}")
        print(f"Re-run to retry failed tasks (reads {init_err_f})")
    return len(err) == 0


def main():
    parser = argparse.ArgumentParser(description="Scrape hitomi.la dataset into SQLite")
    parser.add_argument('--workers', type=int, default=2, help='concurrent fetch workers (default: 2)')
    parser.add_argument('--max-retries', type=int, default=3, help='max retries per request (default: 3)')
    parser.add_argument('--timeout', type=int, default=10, help='request timeout in seconds (default: 10)')
    parser.add_argument('--only-failed', action='store_true', help='only retry previously failed tasks')
    args = parser.parse_args()

    db_p = temp_p.joinpath("hitomi.db")
    Db.create_tables(db_p)
    success = scrape_and_save(db_p, workers=args.workers, max_retries=args.max_retries, timeout=args.timeout)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
