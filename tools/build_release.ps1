<#
.SYNOPSIS
  PA Agent 打包脚本：PyInstaller 构建 → 压缩 → （可选）创建 GitHub Release。

.DESCRIPTION
  产物在 dist/PA_Agent/（文件夹版，用户数据写在 exe 同级目录）。
  依赖：python -m pip install -e . pyinstaller

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
  powershell -ExecutionPolicy Bypass -File tools/build_release.ps1 -Tag v0.1.0 -Publish
#>
param(
    [string]$Tag = "",
    [switch]$Publish,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host ""; Write-Host "=== $msg ===" -ForegroundColor Cyan }

Step "环境检查"
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { throw "缺少 PyInstaller：python -m pip install pyinstaller" }
if (-not (Test-Path "PA_Agent.spec")) { throw "找不到 PA_Agent.spec" }

if (-not $SkipTests) {
    Step "回归测试"
    python -m pytest -m "not live" --ignore=tests/e2e -q
    if ($LASTEXITCODE -ne 0) { throw "测试未通过，已中止打包" }
}

Step "清理旧产物"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Step "PyInstaller 构建"
python -m PyInstaller --noconfirm --clean PA_Agent.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

$Exe = Join-Path $Root "dist\PA_Agent\PA_Agent.exe"
if (-not (Test-Path $Exe)) { throw "构建产物缺失：$Exe" }

Step "清理冒烟测试残留"
# A local smoke run writes settings.json / logs / records next to the exe.
# Shipping those would hand the user someone else's state -- the app must
# create them on first run, and logs/records are gitignored runtime data.
foreach ($stale in @("config\settings.json", "logs", "records", "trade_records", "experience")) {
    $path = Join-Path "$Root\dist\PA_Agent" $stale
    if (Test-Path $path) { Remove-Item $path -Recurse -Force; Write-Host "removed $stale" }
}

Step "附带使用文档"
New-Item -ItemType Directory -Force -Path "dist\PA_Agent\config" | Out-Null
# config\README.md must land in config\, not at the root -- both are "README.md".
$docs = @{
    "README.md"                        = "README.md"
    "PA_Agent使用文档.md"              = "PA_Agent使用文档.md"
    "LICENSE"                          = "LICENSE"
    "config\README.md"                 = "config\README.md"
    "config\settings.example.json"     = "config\settings.example.json"
}
foreach ($entry in $docs.GetEnumerator()) {
    $src = Join-Path $Root $entry.Key
    if (Test-Path $src) {
        Copy-Item $src (Join-Path "$Root\dist\PA_Agent" $entry.Value) -Force
    }
}

if (-not $Tag) {
    $Tag = "v" + (python -c "import pa_agent; print(pa_agent.__version__)").Trim()
}

Step "压缩 ($Tag)"
$Zip = Join-Path $Root "dist\PA_Agent-$Tag-win64.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path "dist\PA_Agent\*" -DestinationPath $Zip -CompressionLevel Optimal
$sizeMb = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
Write-Host "产物：$Zip ($sizeMb MB)" -ForegroundColor Green

if ($Publish) {
    Step "发布 GitHub Release $Tag"
    git rev-parse $Tag 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        git tag -a $Tag -m "PA Agent $Tag"
        git push origin $Tag
    }
    gh release view $Tag 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        gh release upload $Tag $Zip --clobber
    } else {
        gh release create $Tag $Zip --title "PA Agent $Tag" --generate-notes
    }
    if ($LASTEXITCODE -ne 0) { throw "GitHub Release 发布失败" }
}

Step "完成"
Write-Host "可执行文件：$Exe" -ForegroundColor Green
