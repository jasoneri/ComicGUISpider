from __future__ import annotations

from GUI.tray.app import TrayApp


def main() -> int:
    return int(TrayApp().run())


if __name__ == "__main__":
    raise SystemExit(main())
