# 💻 macOS Deploy

## 🚩 Architecture related

Check the architecture with the following command (generally `x86_64` for Intel chips and `arm64` for Apple chips)  

```bash
python -c "import platform; print(platform.machine())"
```

1. `x86_64` architecture: The developer virtual machine is generally this architecture, and you can follow the process below  
2. `arm64` architecture: CGS-init.app will automatically install `Rosetta 2`, and some [solutions to the error message](#trying-for-pop-up-error-messages) are listed below

## Portable Package

macOS only needs to download the `CGS-macOS` compressed package

::: details Unzip directory tree (click to expand)

```
  CGS-macOS
   ├── CGS.app                     # Both the *main executor* and a code directory, it same as execute script `scripts/deploy/launcher/mac/CGS.bash`
   |    ├── Contents
   |         ├── Resources
   |              ├── scripts      # Real project code directory
   ├── CGS-init.app                # Execute the script `scripts/deploy/launcher/mac/init.bash`
   └── CGS_macOS_first_guide.html  # Used as a one-time guide for the first use after unzipping
```

:::

## Operation

::: warning All documents containing the `scripts` directory
Including this Deployment document, the main README, releases page, issue, etc.,  
The absolute-path in the app after moving to the application is `/Applications/CGS.app/Contents/Resources/scripts`
:::

::: warning Execute the following initialization steps
All `.app` must be opened with the right mouse button and clicked cancel the first time,  
then opened with the right mouse button to have an option to open,  
and then opened with a double-click from then on  
:::

|       | Explanation                                                                                                                                                                                                                                                                           |
|:------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| initialization | ⚠️following steps must be executed in strict order<br>1. After each decompression, move `CGS.app` to the application (see below for the figure)<br>2. After each unzip, you must run `CGS-init.app` to check/install environment,<br>⚠️ _**Note the new terminal window and follow the prompts**_ ⚠️ (corresponding to step 1.5 to change the font, you can repeat step 2) |

<table><tbody>  
    <tr><td>app move to Applications</td><td><img alt="" src="../../../assets/img/deploy/mac-app-move.jpg"></td></tr>  
</tbody></table>

## 🔰 Others

### Trying for pop-up error messages

```bash
# arm64 CGS.app shows corrupted and cannot be opened
/opt/homebrew/bin/python3.12 /Applications/CGS.app/Contents/Resources/scripts/CGS.py
# or
/usr/local/bin/python3.12 /Applications/CGS.app/Contents/Resources/scripts/CGS.py
```

::: info If both fail, you can try to find methods by chatgpt / feedback in the group
:::

### Updating

⚠️ Configuration files / deduplication records are stored in `scripts`, please be careful not to lose them by directly overwriting when downloading packages
If there are UI/Interface changes, it is recommended to run `CGS-init.app` to ensure that the font settings are correct

### Bug report / submit issue

When running software on macOS and encountering errors that need to be reported as issues, in addition to selecting `macOS` in the system, 
you also need to specify the system version and architecture in the description  
(Developer development environment is `macOS Sonoma(14) / x86_64`)
