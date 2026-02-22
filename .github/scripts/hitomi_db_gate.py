"""Quality gate for hitomi.db - validates integrity before release."""
import sys
import sqlite3
from contextlib import closing

EXPECTED_TABLES = 108  # 4 categories x 27 letters
MIN_TOTAL_ROWS = 5000

CATEGORIES = ['tags', 'artists', 'series', 'characters']
LETTERS = [*[chr(i) for i in range(97, 123)], '123']


def check(db_path):
    errors = []

    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()

        # integrity check
        result = cursor.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            errors.append(f"integrity_check failed: {result}")
            print("\n".join(errors))
            return False

        # table existence + non-empty
        total_rows = 0
        missing = []
        empty = []

        for cat in CATEGORIES:
            for letter in LETTERS:
                table_name = f"all{cat}-{letter}"
                try:
                    count = cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`").fetchone()[0]
                    total_rows += count
                    if count == 0:
                        empty.append(table_name)
                except sqlite3.OperationalError:
                    missing.append(table_name)

        if missing:
            errors.append(f"missing tables ({len(missing)}): {missing[:5]}...")
        if empty:
            # empty tables are warnings, not errors (some letters may legitimately have no data)
            print(f"[WARN] empty tables ({len(empty)}): {empty[:10]}...")

        found = EXPECTED_TABLES - len(missing)
        if found < EXPECTED_TABLES:
            errors.append(f"table count: {found}/{EXPECTED_TABLES}")

        if total_rows < MIN_TOTAL_ROWS:
            errors.append(f"total rows {total_rows} < minimum {MIN_TOTAL_ROWS}")

        # language table
        try:
            cursor.execute("SELECT COUNT(*) FROM `language`")
        except sqlite3.OperationalError:
            errors.append("language table missing")

    if errors:
        print("[FAIL] Quality gate errors:")
        for e in errors:
            print(f"  - {e}")
        return False

    print(f"[PASS] {found} tables, {total_rows} total rows")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: hitomi_db_gate.py <db_path>")
        sys.exit(1)
    sys.exit(0 if check(sys.argv[1]) else 1)
