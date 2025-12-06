# 🚀 Quick-Start

## 1. Download / Deploy

+ Directly download [📦portable-pkg](https://github.com/jasoneri/ComicGUISpider/releases/latest), and unzip

::: warning macOS
need readed [macOS Deploy](./mac-required-reading.md) document
:::

+ Or use [astral-sh/uv](https://github.com/astral-sh/uv) ( easily install by `brew install uv`, or [remote installation script](https://docs.astral.sh/uv/#installation) )  

```bash
uv tool install comicguispider --python "<3.14"
uv tool update-shell
```

## 2. Usage

### GUI

```bash
cgs
```

### CLI

```bash
cgs-cli --help
```

## 3. Configuration

If you have needs of custom requirements, reference [🔨Configuration](../config/index.md) for settings

## 4. Update

+ CGS innerded an update module, you can click the `Update` button in the configuration window to update
::: info When `local version` < `latest stable version` < `latest dev version`
You need to update to `latest stable version` before you can update to `latest dev version`
:::

+ or `uv tool` install specified version such as `2.5.0`
```zsh
uv tool install ComicGUISpider==2.5.0 --force --python "<3.14"
```

+ or win-portable-exe install specified version such as `2.5.0`  
need `_pystand_static.int` first-line version of `v1`

```cmd
.\CGS.exe -v 2.5.0
```
