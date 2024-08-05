## Contents

```shell
script
  ├── __init__.py
  ├── conf.yml                # config share publicly for all inside of the folder-script
  ├── extra.py                # for temp single task 
  ├── image
       ├── __init__.py
       ├── kemono.py          # support patreon/fanbox/fantia etc
       └── saucenao.py        # get High-Definition image from search of saucenao
  └── script.md
```

### format of `script/conf.yml`

```yaml
kemono:
  sv_path: D:\pic\kemono
  cookie: eyJfcGVybWaabbbW50Ijxxxxxxxxxxxxxxxxxxxxx   # get it by login-account https://kemono.su/api/schema, F12, field session of cookie
  redis_key: kemono

proxies:
  - 127.0.0.1:12345
redis:
  host: 127.0.0.1
  port: 6379
  db: 0
  password:
```

some package of this script module don't exist in requirements.txt, <br>
as it can run independently(except `from utils import Conf, ori_path`)

## Note

> this scripts require knowledge of backend such as redis(etc.)

> No plans for GUI-development for it in recent time
