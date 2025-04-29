import re
import json
import sqlite3
from contextlib import closing
import httpx
from lxml import html

from assets import res
from utils import ori_path, temp_p, conf


BASE_URL = "https://hitomi.la/all{category}-{letter}.html"
CATEGORIES = ['tags', 'artists', 'series', 'characters']
LETTERS = [*[chr(i) for i in range(97, 123)], '123']
db_p = ori_path.joinpath('assets/hitomi.db')
proxy = (conf.proxies or [None])[0]
client = httpx.Client(http2=True, 
    headers={
        "accept": "*/*",
        "accept-language": res.Vars.ua_accept_language,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "referer": "https://hitomi.la/"
    }
)
if proxy:
    client.proxies = {'http://':  'http://{proxy}', 'https://': 'http://{proxy}'}


def lstrip(text):
    if text.startswith("all"):
        return text[3:]
    return text


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
    def create_tables(cls):
        with closing(sqlite3.connect(db_p)) as db_conn:
            cursor = db_conn.cursor()
            for category in CATEGORIES:
                for letter in LETTERS:
                    table_name = f"all{lstrip(category)}-{letter}"
                    cursor.execute(cls.data_tb % table_name)
            cursor.execute(cls.language_tb)
            db_conn.commit()

    @classmethod
    def recreate(cls, table_name):
        with closing(sqlite3.connect(db_p)) as db_conn:
            cursor = db_conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
            cursor.execute(cls.data_tb % table_name)
            db_conn.commit()

regex = re.compile('.*/(.*?)-all')
digit_regex = re.compile(r'\d+')


def scrape_and_save():
    def scrape(category, letter):
        def get_content(_category, _letter):
            resp = client.get(BASE_URL.format(category=_category, letter=_letter), timeout=10)
            resp.raise_for_status()
            content = resp.content
            return content
        tree = html.fromstring(get_content(category, letter))
        lis = tree.xpath('//ul[@class="posts"]/li')
        items = [
            (regex.search(li.xpath('./a/@href')[0]).group(1),
                int(''.join(digit_regex.findall(li.xpath('.//text()')[-1]))))
            for li in lis
        ]
            
        table_name = f"all{category}-{letter}"
        if tb_rewrite_flag:
            Db.recreate(table_name)
        with closing(db_conn.cursor()) as cursor:
            cursor.executemany(
                f"INSERT OR IGNORE INTO `{table_name}` (content,num) VALUES (?,?)",
                [item for item in items if item[0].strip()]
            )
            db_conn.commit()
            print(f"[SUCCESS] {table_name} writen {cursor.rowcount} ")
    err = []
    init_err_f = temp_p.joinpath('hitomi_db_init_err.json')
    tb_rewrite_flag = False
    if init_err_f.exists():
        with open(init_err_f, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        tb_rewrite_flag = True
    if not tasks:
        tasks = [f'{category}-{letter}' for category in CATEGORIES for letter in LETTERS]
    with closing(sqlite3.connect(db_p)) as db_conn:
        for task in tasks:
            category, letter = task.split('-')
            category = lstrip(category)
            try:
                scrape(category, letter)
            except Exception as e:
                print(f"[ERROR] {task} {e}")
                err.append(f'{category}-{letter}')
    with open(init_err_f, 'w', encoding='utf-8') as f:
        json.dump(err, f, ensure_ascii=False, indent=4)


def main():
    Db.create_tables()
    scrape_and_save()
