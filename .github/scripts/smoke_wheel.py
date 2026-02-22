import os
import subprocess
import sys


def run_test(name, cmd, env):
    print(f"::group::{name}")
    result = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    print(f"exit_code={result.returncode}")
    print("::endgroup::")
    return result.returncode


def main():
    env = os.environ.copy()
    tests = [
        ("entrypoint import", [sys.executable, "-c", "import CGS"]),
        ("check mode startup", [sys.executable, "-c", "import CGS; CGS.start()"]),
        ("cli help", ["cgs-cli", "--help"]),
    ]

    failures = []
    for name, cmd in tests:
        if run_test(name, cmd, env) != 0:
            failures.append(name)

    if failures:
        raise SystemExit(f"Smoke tests failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
