# 💻 macOS Deploy

## 📑 Description

::: tip protable-pkg after version of v2.4.0-beta also same used with `uv tool`

---

so recommended directly: [uv tool install](/locate/en/deploy/quick-start)
:::

## Operation

::: tip single init command

```bash
curl -fsSL https://raw.githubusercontent.com/jasoneri/ComicGUISpider/GUI/deploy/launcher/mac/init.bash | bash
```

:::

::: warning source code path

```bash
echo "$(uv tool dir)/comicguispider/Lib/site-packages"
```

:::

::: warning Execute the following initialization steps
All `.app` must be opened with the right mouse button and clicked cancel the first time,  
then opened with the right mouse button to have an option to open,  
and then opened with a double-click from then on  
:::


## 🔰 Others

### Trying for pop-up error messages

```bash
cgs
# or
uv tool run --from comicguispider cgs
```

::: info If both fail, you can try to find methods by chatgpt / feedback in the group
:::

### Bug report / submit issue

When running software on macOS and encountering errors that need to be reported as issues, in addition to selecting `macOS` in the system, 
you also need to specify the system version and architecture in the description  
(Developer development environment is `macOS Sonoma(14) / x86_64`)
