# 💻 macOS Deploy

## 📑 Description

::: tip protable application after version of v2.4.0 is nolonger support except of chinese user, as script of CGS.app use gitee instead of github, and pypi chinese mirror.
but it still easily install or use CGS by  `uv tool`, take a look for [uv tool install](/locate/en/deploy/quick-start), my friends.
:::

## Operation

::: warning source code path

```bash
echo "$(uv tool dir)/comicguispider/Lib/site-packages"
```

:::


## 🔰 Others

### Trying for pop-up error messages

```bash
cgs
# or
uv tool run --from comicguispider cgs
```

### Bug report / submit issue

When running software on macOS and encountering errors that need to be reported as issues, in addition to selecting `macOS` in the system, 
you also need to specify the system version and architecture in the description  
(Developer development environment is `macOS Sonoma(14) / x86_64`)

::: tip get architecture
```bash
python -c "import platform; print(platform.machine())"
```
:::