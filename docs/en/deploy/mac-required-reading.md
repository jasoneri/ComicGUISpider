# 💻 macOS Deploy

## 📑 Description

::: tip Portable application versions after v2.4.0 are no longer supported except for Chinese users, as the script of CGS.app uses Gitee instead of GitHub and the Chinese PyPI mirror.
but it still easily install or use CGS by  `uv tool`, take a look for [uv tool install](/en/deploy/quick-start), my friends.
:::

## Operation

::: warning source code path

```bash
echo "$(uv tool dir)/comicguispider/Lib/site-packages"
```

:::


## 🔰 Others

### Bug report / submit issue

When running software on macOS and encountering errors that need to be reported as issues, in addition to selecting `macOS` in the system, 
you also need to specify the system version and architecture in the description  
(Developer development environment is `macOS Sonoma(14) / x86_64`)

::: tip get architecture
```bash
uv run python -c "import platform; print(platform.machine())"
```
:::
