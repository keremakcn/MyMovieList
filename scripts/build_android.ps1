param([switch]$Release, [string]$Python = '', [string]$Gradle = '.\gradlew.bat')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$Python) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
if ($Release -and !(Test-Path -LiteralPath (Join-Path $root 'android\keystore.properties'))) {
    throw 'Release signing is not configured. Run scripts/create_android_signing.ps1 once, then back up the private signing files.'
}
$previousPython = $env:CHAQUOPY_BUILD_PYTHON
$env:CHAQUOPY_BUILD_PYTHON = $Python
Push-Location -LiteralPath (Join-Path $root 'android')
try {
    if ($Release) { & $Gradle --no-daemon assembleRelease bundleRelease }
    else { & $Gradle --no-daemon assembleDebug }
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
    $versionSource = Get-Content -LiteralPath (Join-Path $root 'version.py') -Raw
    if ($versionSource -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') { throw 'Cannot read version.' }
    $baseVersion = $Matches[1]
    $version = "$baseVersion-android-beta.1"
    $destination = Join-Path $root "dist\android\$version"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    if ($Release) {
        Copy-Item -LiteralPath app/build/outputs/apk/release/app-release.apk -Destination (Join-Path $destination "MyMovieList-$version.apk") -Force
        Copy-Item -LiteralPath app/build/outputs/bundle/release/app-release.aab -Destination (Join-Path $destination "MyMovieList-$version.aab") -Force
    } else {
        Copy-Item -LiteralPath app/build/outputs/apk/debug/app-debug.apk -Destination (Join-Path $destination "MyMovieList-$version-debug.apk") -Force
    }
    Get-ChildItem -LiteralPath $destination -File | Where-Object { $_.Extension -in '.apk', '.aab' } | ForEach-Object {
        '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
    } | Set-Content -LiteralPath (Join-Path $destination 'SHA256SUMS.txt') -Encoding ascii
    Write-Output "Android output: $destination"
} finally {
    Pop-Location
    $env:CHAQUOPY_BUILD_PYTHON = $previousPython
}
