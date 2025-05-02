# 设置输出编码为 UTF-8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 颜色定义
$RED = "`e[31m"
$GREEN = "`e[32m"
$YELLOW = "`e[33m"
$BLUE = "`e[34m"
$NC = "`e[0m"

# 获取当前脚本路径
$scriptDir = $PSScriptRoot
if (-not (Test-Path -Path $scriptDir)) {
    $proj_p = Get-Location
}
else {
    $level = 3
    for ($i=0; $i -lt $level; $i++) {
        $scriptDir = Split-Path -Path $scriptDir -Parent
    }
    $proj_p = $scriptDir
}
echo $proj_p

$uv_bin = Join-Path -Path $proj_p -ChildPath "runtime/uv.exe"
echo $uv_bin
$python_exe = Join-Path -Path $proj_p -ChildPath "runtime/python.exe"
echo $python_exe

# 检查 python.exe 是否存在
if (-not (Test-Path -Path $python_exe)) {
    Write-Host "runtime/python.exe not found, need excute on unzipped path/请在解压的根目录下执行" -ForegroundColor Red
    pause
    exit
}

# zh-CN 则加速github
$uiCulture = [System.Threading.Thread]::CurrentThread.CurrentUICulture
function SpeedUp-Github {
    param ([string]$url)
    if ($uiCulture.Name -eq "zh-CN") {
        $url = "https://gitproxy.click/" + $url
    }
    return $url
}
$uv_url = SpeedUp-Github "https://github.com/jasoneri/imgur/releases/download/preset/uv.exe"

# 下载 uv
if (-not (Test-Path -Path $uv_bin)) {
    try {
        Write-Host "$BLUE downloading uv from $uv_url $NC"
        Invoke-WebRequest -Uri $uv_url -OutFile $uv_bin
        Write-Host "$GREEN downloaded, saved to $uv_bin $NC"
    }
    catch {
        Write-Host "downloading uv failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}
else {
    Write-Host "$GREEN uv already exists, skipping download. $NC"
}

# 下载 requirements.txt
$requirements_file = Join-Path -Path $proj_p -ChildPath "scripts\requirements\win.txt"
echo $requirements_file
$requirements_file_url = SpeedUp-Github "https://raw.githubusercontent.com/jasoneri/ComicGUISpider/refs/heads/GUI/requirements/win.txt"
try {
    Write-Host "$BLUE downloading requirements file from $requirements_file_url $NC"
    Invoke-WebRequest -Uri $requirements_file_url -OutFile $requirements_file
    Write-Host "$GREEN downloaded, saved to $requirements_file $NC"
}
catch {
    Write-Host "downloading requirements file failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 安装依赖
if ($uiCulture.Name -eq "zh-CN") {
    & "$uv_bin" pip install -r $requirements_file --python "$python_exe" --index-url http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
} else {
    & "$uv_bin" pip install -r $requirements_file --python "$python_exe"
}