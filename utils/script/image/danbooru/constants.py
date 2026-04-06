from __future__ import annotations

import re

SUPPORTED_MEDIA_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
UNSUPPORTED_MEDIA_EXTENSIONS = {"mp4", "webm", "zip"}
DANBOORU_SQL_TABLE = "danbooru_md5_table"
DANBOORU_BASE_URL = "https://danbooru.donmai.us"
AUTOCOMPLETE_PATH = "/autocomplete"
DEFAULT_DOWNLOAD_CONCURRENCY = 3
MOTRIX_POLL_INTERVAL = 1.2
DANBOORU_PAGE_SIZE = 30
DANBOORU_AUTOCOMPLETE_LIMIT = 20
DEFAULT_DANBOORU_SAVE_PATH = "D:/pic/danbooru"
DANBOORU_SAVE_TYPE_SEARCH_TAG = "search_tag"

_WHITESPACE_RE = re.compile(r"\s+")
_ORDER_TOKEN_CAPTURE_RE = re.compile(r"(?:^|\s)(order:[^\s]+)")
_ORDER_TOKEN_STRIP_RE = re.compile(r"(?:^|\s)order:[^\s]+")
DANBOORU_CHALLENGE_MARKERS = (
    "cf-mitigated",
    "challenge-form",
    "cf-browser-verification",
    "just a moment",
    "__cf_chl_",
)
_DANBOORU_BROWSER_HEADER_DROP = frozenset(
    {
        "accept-encoding",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

DANBOORU_OFFICIAL_ORDER_VALUES = frozenset(
    {
        "active_child_count","active_children","active_children_asc","active_comment_count","active_comments",
        "active_comments_asc","active_note_count","active_notes","active_notes_asc","active_pool_count","active_pools",
        "active_pools_asc","appeal_count","appeals","appeals_asc","approval_count","approvals","approvals_asc",
        "artcomm","artcomm_asc","arttags","arttags_asc","change","change_asc","chartags","chartags_asc",
        "child_count","children","children_asc","collection_pool_count","collection_pools","collection_pools_asc",
        "comment","comment_asc","comment_bumped","comment_bumped_asc","comment_count","comments","comments_asc",
        "copytags","copytags_asc","created_at","created_at_asc","custom","deleted_child_count","deleted_children",
        "deleted_children_asc","deleted_comment_count","deleted_comments","deleted_comments_asc","deleted_note_count",
        "deleted_notes","deleted_notes_asc","deleted_pool_count","deleted_pools","deleted_pools_asc","disapproved",
        "disapproved_asc","downvotes","downvotes_asc","duration","duration_asc","favcount","favcount_asc","filesize",
        "filesize_asc","flag_count","flags","flags_asc","gentags","gentags_asc","id","id_desc","landscape","md5",
        "md5_asc","metatags","metatags_asc","modqueue","mpixels","mpixels_asc","none","note","note_asc","note_count",
        "notes","notes_asc","pool_count","pools","pools_asc","portrait","random","rank","replacement_count",
        "replacements","replacements_asc","score","score_asc","series_pool_count","series_pools","series_pools_asc",
        "tagcount","tagcount_asc","upvotes","upvotes_asc",
    }
)

DANBOORU_SORT_OPTIONS = (
    ("默认", ""),
    ("评分", "score"),
    ("最旧", "id"),
)
