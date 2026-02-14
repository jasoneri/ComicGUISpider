# ✒️ Development Guide

Future updates will be based on AI rules/workflows/skills for unified testing standards.

## Spider Development

#### Prerequisites

Target website search URL (search_url), search page HTML (search.html),
book page URL (book_url), book page HTML (book.html)

#### Development Process

1. Clone this project locally, using mainstream models/CLI tools (Claude Code/Codex)
2. Add the two URL values from step one to the prompt below, upload/specify the two HTML files, and send the prompt to the AI

::: details Prompt Reference

```text
search_url=
book_url=

As a crawler engineer proficient in Python and Scrapy with excellent coding standards, you need to extend this project to support a new website.

## Local Development

Please complete the development in the following four parts:

**Part 1: Spider Class Development**

1. If the user hasn't named the target website, extract a name from the search_url domain. The following instructions will use `abcdefg` as a placeholder
2. Create a new spider file in the `ComicSpider/spiders/` directory (e.g., `abcdefg.py`)
3. Implement the Spider class with the following required attributes and methods:
   - name: Spider name (use target website domain or title)
   - domain: Full domain of the target website
   - search_url_head: Search page URL prefix (excluding keyword part)
4. Reference the existing [WnacgSpider](ComicSpider/spiders/wnacg.py) implementation
5. Discuss with the user whether the target website requires a proxy to access, to determine if custom_settings should include ComicDlProxyMiddleware / ComicDlAllProxyMiddleware

**Part 2: Utils Class Development (Parsing)**

1. Implement the corresponding Utils parsing class in the `utils/website/` directory, using PascalCase naming: AbcdefgUtils
2. Inherit from the correct base class depending on website type (regular comic sites and 18+ sites have different base classes)
3. Implement the following required attributes and methods:
   - name: abcdefg
   - uuid_regex: Regular expression to extract work ID from preview URL
   - parse_search: Method to parse search.html, locate elements, and call parse_search_item to get a list of BookInfo objects
   - parse_search_item: Takes a single located element as parameter, returns a BookInfo object
   - parse_book: Method to parse book.html into a BookInfo object
4. After completion, register the Utils class in spider_utils_map

**Part 3: UI Configuration**

1. Add configuration in `variables/__init__.py`:
   - SPIDERS: Add new index and spider name
   - DEFAULT_COMPLETER: Add index and default preset mapping (can be empty list)
   - STATUS_TIP: Add index and status bar tip text (can be empty string)
   - For 18+ websites: Add spider name to SPECIAL_WEBSITES, add index to SPECIAL_WEBSITES_IDXES
   - If preview images require proxy access: Add index to CN_PREVIEW_NEED_PROXIES_IDXES

2. Add dropdown option in the setupUi method of `GUI/mainwindow.py`:
self.chooseBox.addItem("")
self.chooseBox.setItemText(index, _translate("MainWindow", "index, website_name"))

**Part 4: Testing**

1. Non-GUI test: Run `python crawl_only.py -w index -k keyword -i 1` to verify basic spider functionality
2. GUI test: Run `python CGS.py` for complete testing:
   - Test the full workflow for the new website (search, download, etc.)
3. Note the log configuration: LOG_FILE in `ComicSpider/settings.py`

**Output Requirements:**
- Provide complete, runnable code
- Code must comply with PEP 8 standards
- XPath selectors must be accurate and reliable
- Add necessary comments
- Ensure proper error handling mechanisms
```

:::

## Notes

AI as a tool is not always reliable. When unexpected deviations occur during AI-assisted development, first try to resolve them using your own code/documentation reading abilities.
