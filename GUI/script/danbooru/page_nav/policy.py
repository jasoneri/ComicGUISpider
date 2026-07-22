from __future__ import annotations

from typing import Optional

from .model import JumpDecision, PageNavState, PageNavTier


class PageNavPolicy:
    def __init__(
        self,
        *,
        small: int = 20,
        medium: int = 100,
        home_jump_max: int = 10,
        window_mid: int = 10,
        window_large: int = 5,
        home_window: int = 5,
        site_cap: int = 1000,
    ):
        self.small = int(small)
        self.medium = int(medium)
        self.home_jump_max = int(home_jump_max)
        self.window_mid = int(window_mid)
        self.window_large = int(window_large)
        self.home_window = int(home_window)
        self.site_cap = int(site_cap)

    def resolve_tier(self, state: PageNavState) -> PageNavTier:
        if state.query_is_empty:
            return PageNavTier.HOME
        total_pages = state.total_pages
        if total_pages is None:
            return PageNavTier.MEDIUM
        if total_pages <= self.small:
            return PageNavTier.SMALL
        if total_pages <= self.medium:
            return PageNavTier.MEDIUM
        return PageNavTier.LARGE

    def fab_label(self, state: PageNavState) -> str:
        current_page = max(1, int(state.current_page or 1))
        if state.query_is_empty:
            if state.total_pages is not None:
                return f"{current_page}/≤{state.site_cap}"
            return str(current_page)
        if state.total_pages is not None:
            return f"{current_page}/{state.total_pages}"
        return str(current_page)

    def panel_hint(self, state: PageNavState) -> str:
        tier = self.resolve_tier(state)
        if tier is PageNavTier.HOME:
            return "首页结果极大：建议加 tag 再深跳；可跳范围受软上限限制"
        if state.total_pages is None:
            return "总页数未就绪，可输入页码尝试跳转"
        if tier is PageNavTier.LARGE:
            return f"共 {state.total_pages} 页（站点 cap {state.site_cap}）；深页可能较慢"
        return f"共 {state.total_pages} 页"

    def max_jump_page(self, state: PageNavState) -> int:
        if state.query_is_empty:
            soft_max = max(1, int(state.current_page) + self.home_jump_max)
            hard_max = state.site_cap
            if state.total_pages is not None:
                hard_max = min(hard_max, state.total_pages)
            return min(soft_max, hard_max)
        if state.total_pages is not None:
            return max(1, min(state.total_pages, state.site_cap))
        return state.site_cap

    def clamp_jump(self, state: PageNavState, requested: int) -> JumpDecision:
        try:
            target = int(requested)
        except (TypeError, ValueError):
            return JumpDecision(accepted=False, target_page=None, reason="invalid")
        if target < 1:
            return JumpDecision(accepted=False, target_page=None, reason="below_min")
        max_page = self.max_jump_page(state)
        if state.query_is_empty and target > max_page:
            return JumpDecision(accepted=False, target_page=max_page, reason="home_soft_cap")
        if target > max_page:
            return JumpDecision(accepted=False, target_page=max_page, reason="above_cap")
        if target == int(state.current_page) and not state.loading:
            return JumpDecision(accepted=False, target_page=target, reason="same_page")
        return JumpDecision(accepted=True, target_page=target, reason="ok")

    def visible_page_items(self, state: PageNavState) -> list[Optional[int]]:
        """Return page numbers and None for ellipsis gaps."""
        current_page = max(1, int(state.current_page or 1))
        tier = self.resolve_tier(state)

        if tier is PageNavTier.HOME:
            low = max(1, current_page - self.home_window)
            high = current_page + self.home_window
            high = min(high, self.max_jump_page(state))
            return list(range(low, high + 1))

        total_pages = state.total_pages
        if total_pages is None:
            low = max(1, current_page - self.window_mid)
            high = current_page + self.window_mid
            high = min(high, state.site_cap)
            return self._with_first_last(low, high, first=1, last=None)

        total_pages = max(1, int(total_pages))
        if tier is PageNavTier.SMALL:
            return list(range(1, total_pages + 1))

        half = self.window_mid if tier is PageNavTier.MEDIUM else self.window_large
        low = max(1, current_page - half)
        high = min(total_pages, current_page + half)
        return self._with_first_last(low, high, first=1, last=total_pages)

    @staticmethod
    def _with_first_last(
        low: int,
        high: int,
        *,
        first: int,
        last: Optional[int],
    ) -> list[Optional[int]]:
        items: list[Optional[int]] = []
        if first < low:
            items.append(first)
            if first + 1 < low:
                items.append(None)
        items.extend(range(low, high + 1))
        if last is not None and last > high:
            if last - 1 > high:
                items.append(None)
            items.append(last)
        return items
