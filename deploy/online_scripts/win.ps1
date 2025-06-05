$IsPwsh = $PSVersionTable.PSEdition -eq "Core"

$proj_p = Get-Location

$python_exe = Join-Path $proj_p "runtime/python.exe"
if (-not (Test-Path $python_exe)) {Write-Output "runtime/python.exe not found, need excute on unzipped path/请在解压的根目录下执行";pause;exit}

$locale = if ($IsPwsh) { (Get-Culture).Name } else { [System.Threading.Thread]::CurrentThread.CurrentUICulture.Name }

$targetUrl = if ($locale -eq "zh-CN") {"https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/pkg_mgr.py"} else {"https://raw.githubusercontent.com/jasoneri/ComicGUISpider/refs/heads/GUI/deploy/pkg_mgr.py"}

$pyPath = "$proj_p\pkg_mgr.py"
try {
    if ($PSVersionTable.PSVersion.Major -le 5) {
        Add-Type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint s, X509Certificate c, WebRequest r, int e) { return true; }
}
"@
        [Net.ServicePointManager]::CertificatePolicy = [TrustAllCertsPolicy]::new()
    }
    Invoke-WebRequest -Uri $targetUrl -OutFile $pyPath -UseBasicParsing
}
catch {
    Write-Output "install pkg_mgr.py failed/下载pkg_mgr.py失败";pause;exit
}
& "$python_exe" "$pyPath" -l $locale
Remove-Item -Path $pyPath -Force