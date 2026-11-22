param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
if (!$Python) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
Push-Location -LiteralPath $root
try {
    $version = & $Python -c 'from version import APP_VERSION; print(APP_VERSION)'
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Cannot read release version.' }
    $name = "MyMovieList-v$version"
    $caFile = (& $Python -c "import os, ssl; p = os.path.join(os.path.dirname(ssl.__file__), 'codex-rejected-cas.pem'); print(p if os.path.isfile(p) else '')").Trim()
    $extraArgs = @()
    if ($caFile) { $extraArgs += @('--add-data', "$caFile;.") }
    & $Python -m PyInstaller --noconfirm --onefile --windowed --name $name --icon=app_icon.ico --add-data 'templates;templates' --add-data 'static;static' --add-data 'supabase/project.json;supabase' @extraArgs run_desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
    & (Join-Path $root "dist\$name.exe") --verify-exe
    if ($LASTEXITCODE -ne 0) { throw 'Compiled desktop executable self-verification failed.' }
    $release = Join-Path $root "dist\releases\v$version"
    New-Item -ItemType Directory -Path $release -Force | Out-Null
    $zip = Join-Path $release "$name-windows.zip"
    # Only these two explicit files enter the public download.
    Compress-Archive -LiteralPath @((Join-Path $root "dist\$name.exe"), (Join-Path $root 'RELEASE_NOTES.md')) -DestinationPath $zip -Force
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $name-windows.zip" | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ascii
    Write-Output "Release files: $release"
} finally {
    Pop-Location
}
