# ✒️ Development Guide

Future updates will be based on AI rules / workflows / skills to unify testing standards.

::: tip Applies to the current provider / runtime architecture
Use the flow below when adding or migrating sites on branches after `2.10-dev`.
:::

## Spider Development

Development setup: clone this project locally with `git`  
Use mainstream models / CLI tools (`claudecode` / `codex` / `cursor`) and similar tools. Do not use pure chat-only models.

### Preparation

Target website

- Search API curl request/response
- Pagination API curl request/response
- Index/update API curl request/response
- (non-R18 manga) book detail > episode list curl request/response
- Book detail/episode detail > page count curl request/response

If known, also prepare:

- Whether proxy / cookies are required
- Whether the site is regular manga or 🔞
- Whether aggr / clip are supported
- Whether dynamic domain / publish page / special referer exists

> After saving the curl materials, give their path to the main agent and ask it to read `docs/en/dev/index.md` `prompt-prepare` and `prompt-dev`
> The main agent owns orchestration and review. First dispatch `prepare agent` serially: validate the request matrix with `prompt-prepare`, then output a material summary consumable by `prompt-dev`
> After the main agent confirms the network chain is feasible, dispatch `dev agent` serially: develop from the material summary with `prompt-dev`
> Finally the main agent reviews diff, verification results, and whether regression handling is needed

::: details prompt-prepare ⇩

```text
site_name=
site_url=

As a developer familiar with Python, httpx, and this repository architecture, you need to prepare request/response fixtures for a new ComicGUISpider site.

## Goal

Based on the provided site_url and known site traits, help complete fixture capture and validation.
All fixtures are for local verification only and must not be tracked by git.

## 1. Fixture capture

1. Open the site in a browser and use DevTools -> Network to capture real requests and responses for each phase
2. For each interaction phase, save one file pair: `<stage>_req.curl` (Copy as cURL) + `<stage>_resp.<html|json>` (response body)
3. Recommended directory: `test/analyze/<site>/`

### Minimum required phases

| Phase | File prefix | Description |
|------|----------|------|
| Search | `search_*` | Search request and result list |
| Book | `book_*` | Book detail page with episode bootstrap |
| Chapter | `chapter_*` | Episode list from XHR or embedded content |
| Section | `section_*` | In-episode image data |

4. Complex sites may also have index (`index_*`), search suggestion (`search_suggest_*`), book metadata XHR (`book_pop_*`), etc. Add them based on real interactions.

## 2. Validation matrix (optional)

1. Write a parser validation script from captured fixtures: `test/net/<site>/transport_matrix.py`
2. Extract key fields for each phase with regex or parsers and output `[OK]` / `[ERR]` reports
3. Confirm HTML/JSON structures can be parsed stably

## 3. Output material summary

Organize validation results in the following format for `prompt-dev`:

site_name: <site English identifier>
site_url: <site index URL>
search_url: <search page URL>
book_url: <book page URL>

**Verified interaction phases**
stages:
  search: <search mode: JSON XHR / HTML pagination / ...>
  book: <book structure: loader bootstrap / direct episode list / ...>
  chapter: <episode source: XHR / embedded HTML / ...>
  pages: <inner-page images: XHR / direct img / ...>

**Site traits**
need_proxy: yes/no
need_cookies: yes/no
site_kind: regular manga / R18
supports_preview: yes/no
supports_aggr: yes/no
supports_clip: yes/no
dynamic_domain: yes/no

## 4. Requirements

- Fixture paths are customizable and do not need to match the examples
- Do not fabricate data; mark uncertain phases as "unverified"
- Expose root causes directly. Do not silently skip or swallow errors
```

:::

#### Actual Development

Fill the previous curl materials, known site traits, and fixture-preparation output into the prompt below, then send it to the AI for execution.

::: details prompt-dev ⇩

```text
search_url=
book_url=
site_name=
need_proxy=
need_cookies=
site_kind=regular manga / R18
supports_preview=
supports_aggr=
supports_clip=

As a developer familiar with Python, Scrapy, httpx, and this repository architecture, you need to extend a new website on the current ComicGUISpider branch.

Read the repository state before coding. Use the current code structure as source of truth.

Current site integration follows the provider-first contract:

- Requests, parsing, preview, cookies/domain/proxy, episode URL locating, and image URL locating live in `utils/website/providers/`
- spider handles Scrapy download assembly
- provider and spider each own their responsibilities; avoid duplicate implementation of the same site rules

## Local development
Complete development in the following six parts:

**1. Baseline search first (must search before generation)**

1. First find 1 to 2 most similar existing sites in the repository as baselines. Read at least:
   - `utils/website/providers/_template.py`
   - `utils/website/providers/<baseline>.py`
   - `ComicSpider/spiders/<baseline>.py` (download assembly reference only)
   - `ComicSpider/spiders/basecomicspider.py`
   - `utils/website/ins.py`
   - `utils/website/registry.py`
   - `utils/website/site_runtime.py`
   - `variables/__init__.py`
   - `GUI/mainwindow.py`
   - `GUI/manager/preprocess.py`
2. Decide whether the new site is a "regular integration" or an "extended integration":
   - Regular integration: provider handles node extraction, search URL, book page, episode, and image page parsing
   - Extended integration: provider also needs request-layer extension, response adaptation, resource locating, dynamic domain / cookies / publish page, or similar capabilities
3. Unify these identifiers before naming:
   - provider `name`
   - download spider `name` (when a spider is really needed)
   - `variables.Spider` enum name
   - `_PROVIDER_BINDINGS` key in `utils.website.ins.py` (bind to the matching `Spider.*`; do not handwrite numeric keys)
   - site display-name mapping in `variables/__init__.py` (`GUI/mainwindow.py` generates dropdown text automatically)
4. If similar site implementations already exist in the current code, do not skip comparison. Extract a capability matrix before development.

**2. Provider part**

1. Create a new provider file under `utils/website/providers/`, preferably starting from `_template.py`
2. Pick the correct mixin / structure based on the site capability combination:
   - Each provider file usually contains three classes: `XxxParser` (inherits `Previewer`, handles parsing), `XxxReqer` (inherits `Req`, handles requests and preview flow), `XxxUtils` (inherits `Utils` + `Previewer`, composes `parser` and `reqer_cls`)
   - R18 sites usually center on `EroUtils`
   - Use `DomainUtils` when dynamic domain is needed
   - Add `Cookies` when cookies are needed
3. Define at least these static configs in `XxxUtils`:
   - `name` / `domain` / `index`
   - `headers` / `book_hea`
   - `uuid_regex` or `get_uuid`
   - `parser` / `reqer_cls` / `__init__` (instantiate `self.reqer` and `self.parser`)
4. `XxxParser` owns parsing methods (`parse_search` / `parse_book` / `parse_search_item` / episode list / reader decoding / image URL construction, etc.)
5. `XxxReqer` owns request and preview async flow. Complex sites may split logic into suitable classes.
6. Add these extension points as needed:
   - `build_preview_search_request()` (Parser classmethod, builds `PreviewRequestSpec` for search)
   - `preview_search()` / `preview_fetch_episodes()` / `preview_fetch_pages()` (Reqer async methods)
   - `preview_client_config()` / `preview_transport_config()` (Utils classmethods)
   - `test_index()`
   - `parse_publish_()`
   - resource locating / response adaptation helpers
   - site-specific exception types
7. Expose root causes directly. Avoid silent empty returns or unexplained compatibility patches.

**3. Spider part**

1. Add or modify `ComicSpider/spiders/<site>.py` only when the site needs the Scrapy download chain
2. Provider-first site download route: download entry consumes the download object populated by provider preview
   - `Spider.mangas()` sites: before submitting to Scrapy, `preview_fetch_pages()` fills `Episode.page_urls`
   - spider side focuses on download assembly. Book page, episode page, and image page parsing close in provider
   - Before development, confirm episode and image page parsing are covered in provider; spider only consumes provider preview-chain results
3. Choose the base class based on download flow:
   - `BaseComicSpider`
   - `BaseComicSpider2`
   - `BaseComicSpider3`
   - `FormReqBaseComicSpider`
4. Only add download fields required by the base class:
   - `name`
   - `domain`
   - `search_url_head`
   - `book_id_url` / `transfer_url` (when required by base class or redirect flow)
   - `mappings` (when still required by base class)
   - `turn_page_search` / `turn_page_info` (when page mapping is still required by base class)
5. Implement only missing download fan-out points:
   - `_process_episode()`: regular manga sites consume `Episode.page_urls` and assemble item; raise a clear error when not populated, as a self-check for the provider preview chain
   - `process_item()`: only for fake request handoff of constructed item
   - `image_request_meta()` (when image requests really need episode referer or other metadata)
   - `custom_settings` (minimal correct middleware / pipeline combination)
6. Close `frame_section()` / `parse_fin_page()` and similar parsing logic in provider. spider should have one download route only.
7. spider consumes provider preview results through the download object. Search, book page, episode page, reader, and image URL parsing are all completed in provider.
8. Add only needed proxy, Referer, or UA support:
   - `ComicDlProxyMiddleware`
   - `ComicDlAllProxyMiddleware`
   - `RefererMiddleware`
   - `UAMiddleware`
   - other site-specific middleware

**4. Registration, GUI, and runtime wiring**

1. Export the new provider in `utils/website/providers/__init__.py`
2. Bind the provider to the matching `Spider` member in `_PROVIDER_BINDINGS` inside `utils/website/ins.py`; `provider_map` expands the rest automatically
3. Sync in `variables/__init__.py`:
   - `Spider` enum
   - `DEFAULT_COMPLETER`
   - `STATUS_TIP`
   - `COOKIES_SUPPORT` (only when login-state cookies are needed; do not write non-login short-lived tokens)
   - capability sets: `specials()` / `mangas()` / `cn_proxy()` / `aggr()` / `clip()`
4. Make the `specials()` and `preview_fetch_episodes()` contract explicit:
   - Sites in `specials()` usually do not need CLI `-i2`
   - Non-`specials()` sites must keep the episode selection chain working
5. Modify `GUI/manager/preprocess.py` only when the site truly needs dedicated preprocessing

**5. Tests and regression**

1. If automated verification is needed, use `unittest`, and let the agent create a test script under `test/` based on this integration
2. These test scripts are local-verification assets by default. The repository owner explicitly requires unittest assets not to be tracked by git
3. Put fixtures under `test/analyze/` or a directory paired with the test script. Do not inline large HTML blocks
4. Run the CLI chain first:
   - `uv run crawl_only.py -w index -k keyword -i 1`
   - For non-`specials()` sites, also run with `-i2 1`
   - For regular manga sites, CLI calls `preview_fetch_pages()` before submitting to Scrapy to populate `Episode.page_urls`
5. Then run the GUI chain:
   - `uv run CGS.py`
6. When needed, let the agent run the matching `uv run python -m unittest ...`
7. Check search, preview, episode selection, download, task panel, and `log/scrapy.log`
8. When encountering compatibility nodes or responsibility-boundary conflicts, list the conflicts and impact first, then decide the implementation

**6. Output requirements**

- Provide complete runnable code
- Modify only files directly related to the target site integration
- Use `uv` by default
- Use `unittest` for tests; if automated verification is needed, let the agent create scripts under `test/`
- Do not add comments unless necessary
- Expose root causes directly. Do not hide error stacks
- After coding, use `$style-refactor` for one structural cleanup pass on this round of changes
- Remind the user that the PR should merge into the latest current `*-dev` branch
```

:::

### Post-development Adjustments

First-pass success is only the baseline. Usually more adjustment is needed.  
At least keep the following working:

1. Index/update API
2. Search API
3. Pagination

It should reach normal list output and download-flow usage.

> [Example PR references](https://github.com/jasoneri/ComicGUISpider/issues?q=state%3Aclosed%20label%3A%22dev%20spider%22)

## Notes

AI as a tool is not always reliable. When expected deviations appear during AI-assisted development, first try to resolve them with your own code / documentation reading ability.

::: details ✒️ Current-architecture site development notes

### 1. Provider Code

Recommended samples:

[Scrapy download assembly: `WnacgSpider`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/wnacg.py)  
[provider sample: `HComicUtils / HComicReqer / HComicParser`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/providers/hcomic.py)  
[provider template: `TemplateUtils`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/providers/_template.py)

#### Provider File Locations

&emsp;✅ Main new-site implementation goes in `utils/website/providers/<site>.py`  
&emsp;✅ Export goes in `utils/website/providers/__init__.py`  
&emsp;✅ Registration goes in `provider_map` in `utils/website/ins.py`

#### Common Provider Responsibilities

&emsp;✅ `name` / `domain` / `index`  
&emsp;✅ `headers` / `book_hea`  
&emsp;✅ `uuid_regex` or `get_uuid()`  
&emsp;✅ `parse_search_item` / `parse_search` / `parse_book`  
&emsp;🔳 `reqer_cls` (split request layer for complex sites)  
&emsp;🔳 `preview_search` / `preview_fetch_episodes` / `preview_fetch_pages`  
&emsp;🔳 `preview_client_config` / `preview_transport_config`  
&emsp;🔳 `test_index`  
&emsp;🔳 `parse_publish_` / dynamic domain / cookies / resource locating rules  
&emsp;🔳 site-specific exception types

> [!tip] The current runtime builds `provider_descriptor_map` and `provider_descriptor_spider_map` from `provider_map` in `utils/website/ins.py` through `registry.py`. Do not update only the provider file when adding a site.

### 2. Spider Code

#### [`ComicSpider/spiders/basecomicspider.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/basecomicspider.py)

Choose the base class after finding the closest site sample:

&emsp;✅ `BaseComicSpider`: common entry  
&emsp;✅ `BaseComicSpider2`: episode page can directly produce final image URLs  
&emsp;✅ `BaseComicSpider3`: multi-hop pagination flow  
&emsp;✅ `FormReqBaseComicSpider`: form-request site

#### Common Spider Responsibilities

&emsp;✅ `name` / `domain` / `search_url_head`  
&emsp;🔳 `book_id_url` / `transfer_url`  
&emsp;🔳 `mappings` / `turn_page_search` / `turn_page_info`  
&emsp;🔳 `preready`  
&emsp;✅ `_process_episode` (regular manga sites only consume already populated `Episode.page_urls`)  
&emsp;🔳 `process_item`  
&emsp;🔳 `image_request_meta`  
&emsp;🔳 `custom_settings` (middleware / pipeline combination)

> [!tip] spider handles download assembly; parsing rules close in provider. Regular manga sites should complete episode and image page data in the provider preview chain. Raise a clear error when `Episode.page_urls` is empty instead of adding another spider-side request route.

### 3. Other Code

#### [`variables/__init__.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/variables/__init__.py)

1. `Spider` - add the enum member first. Capability groups are maintained through classmethods:
   - `specials()`
   - `mangas()`
   - `cn_proxy()`
   - `aggr()`
   - `clip()`
2. `SPIDERS` - generated automatically from the `Spider` enum
3. `SPIDERS_LABELS` / site display-name mapping - source for `chooseBox` text
4. `DEFAULT_COMPLETER` - default preset for the new index
5. `STATUS_TIP` - status-bar tip for the new index
6. `COOKIES_SUPPORT` - add support fields for sites that need cookies

> [!TIP] `specials()` is not only a category label. It directly affects the GUI / CLI download contract; non-`specials()` sites need CLI `-i2/--indexes2`.

### 4. UI Code

#### [`GUI/mainwindow.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/mainwindow.py)

`apply_translations()` rebuilds `chooseBox` from `SPIDERS_LABELS` in `variables.__init__.py`. When adding a site, maintain the display-name mapping on the variables side instead of hand-writing `setItemText()` here.

Only check [`GUI/manager/preprocess.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/manager/preprocess.py) when the site needs extra preprocessing.  
Sites with only `test_index()` can usually use the generic preprocessing path.

### 5. Tests

If automated verification is needed, let the agent create a `unittest` script under `test/` for this integration. It is only for local verification and must not be tracked by git.

#### CLI Chain

```bash
uv run crawl_only.py -w 8 -k test -i 1
```

Non-`specials()` sites need `-i2`:

```bash
uv run crawl_only.py -w 5 -k update -i 1 -i2 1
```

#### GUI Chain

```bash
uv run CGS.py
```

> Note: GUI / Scrapy exceptions still use logs as source of truth. Check `log/scrapy.log` first during troubleshooting. Do not hide root causes by swallowing exceptions.

:::
