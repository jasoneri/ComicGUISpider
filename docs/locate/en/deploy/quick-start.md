# 🚀 Quick-Start

## 1. Download / Deploy

+ Directly download [📦portable-pkg](https://github.com/jasoneri/ComicGUISpider/releases/latest), and unzip

::: warning macOS
need readed [macOS Deploy](./mac-required-reading.md) document
:::

+ Or use [astral-sh/uv](https://github.com/astral-sh/uv)  

```bash
uv tool install comicguispider
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

+ You can also choose to download the latest version manually to the releases, but you need to pay attention to the configuration files and duplicate records not being overwritten and lost
