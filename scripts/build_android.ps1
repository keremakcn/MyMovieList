param([switch]$Release, [switch]$Clean, [string]$Python = '', [string]$Gradle = '.\gradlew.bat')
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
    $buildTasks = @()
    if ($Clean) { $buildTasks += 'clean' }
    if ($Release) { $buildTasks += @('assembleRelease', 'bundleRelease', 'lintRelease') }
    else { $buildTasks += @('assembleDebug', 'lintDebug') }
    & $Gradle --no-daemon @buildTasks
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
    $variant = if ($Release) { 'release' } else { 'debug' }
    $metadataFile = "app/build/outputs/apk/$variant/output-metadata.json"
    $metadata = Get-Content -LiteralPath $metadataFile -Raw | ConvertFrom-Json
    $packages = @($metadata.elements)
    if ($packages.Count -ne 1 -or @($packages[0].filters).Count -ne 0) {
        throw 'Expected one standalone APK, not split APKs.'
    }
    $package = $packages[0]
    $artifactVersion = $package.versionName
    if ($artifactVersion -notmatch '^\d+\.\d+\.\d+-android-beta\.\d+(-debug)?$') {
        throw 'Unexpected Android version in compiled APK metadata.'
    }
    $version = $artifactVersion -replace '-debug$', ''
    $destination = Join-Path $root "dist\android\$version"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    if ($Release) {
        Copy-Item -LiteralPath app/build/outputs/apk/release/app-release.apk -Destination (Join-Path $destination "MyMovieList-$artifactVersion.apk") -Force
        Copy-Item -LiteralPath app/build/outputs/bundle/release/app-release.aab -Destination (Join-Path $destination "MyMovieList-$version.aab") -Force
    } else {
        Copy-Item -LiteralPath app/build/outputs/apk/debug/app-debug.apk -Destination (Join-Path $destination "MyMovieList-$artifactVersion.apk") -Force
    }
    Get-ChildItem -LiteralPath $destination -File | Where-Object { $_.Extension -in '.apk', '.aab' } | ForEach-Object {
        '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
    } | Set-Content -LiteralPath (Join-Path $destination 'SHA256SUMS.txt') -Encoding ascii
    Write-Output "Android output: $destination"
} finally {
    Pop-Location
    $env:CHAQUOPY_BUILD_PYTHON = $previousPython
}
