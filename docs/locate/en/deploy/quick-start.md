# 🚀 Quick-Start

## 1. Download / Deploy

+ Directly download [📦portable-pkg](https://github.com/jasoneri/ComicGUISpider/releases/latest), and unzip

::: warning macOS users
Please read the [macOS deployment](./mac-required-reading.md) document
:::

+ Or clone this project `git clone https://github.com/jasoneri/ComicGUISpider.git`  
You need to install `python3.12+`, the environment package is in the `requirements` in the root directory, install the corresponding architecture with pip

## 2. Usage

### GUI

`python CGS.py`  
Or using Portable-Applications

### CLI

`python crawl_only.py --help`  
Or using env of portable environment:  
`.\runtime\python.exe .\scripts\crawl_only.py --help`

## 3. Configuration

If you have needs of custom requirements, reference [🔨Configuration](../config) for settings

## 4. Update

+ CGS innerded an update module, you can click the `Check for Updates` button in the configuration window to update
::: info When `local version` < `latest stable version` < `latest dev version`
You need to update to `latest stable version` before you can update to `latest dev version`
:::

+ You can also choose to download the latest version manually to the releases, but you need to pay attention to the configuration files and duplicate records not being overwritten and lost
::: tip The configuration file is `scripts/conf.yml` and the duplicate record is `scripts/record.db`
:::
