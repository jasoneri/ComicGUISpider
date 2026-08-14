# -*- coding: utf-8 -*-
"""Subscribe tool package (mid_tool-style module layout).

Layout:
  common.py         — card metrics + pure helpers (no QSS strings)
  workers.py        — cover fetch + DL scan QThreads
  card.py           — SubscribeCard waterfall item
  cover_session.py  — CoverSession (generation-gated cover/DL orchestration)
  library_board.py  — LibraryBoard (FlowLayout cards + filter paint)
  side_panel.py     — SubscribeSidePanel (card-config + binding editor)
  window.py         — SubscribeWindow frameless shell
  __init__.py       — public package surface
"""
from .card import SubscribeCard
from .window import SubscribeWindow

__all__ = (
    "SubscribeCard",
    "SubscribeWindow",
)
