## contents

```shell
script
  ├── __init__.py
  ├── comic_viewer_tools.py   # func of comic_viewer related
  ├── conf.yml                # config share publicly for all inside of the folder-script
  ├── extra.py                # for temp single task 
  ├── image
       ├── __init__.py
       ├── kemono.py          # support patreon/fanbox/fantia etc
       └── saucenao.py        # get High-Definition image from search of saucenao
  └── script.md
```

---
> except of comic_viewer_tools.py embed into ComicGUISpider，
> else of script require knowledge of backend such as redis(etc.)