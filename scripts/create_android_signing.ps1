param([string]$Keytool = 'keytool')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$private = Join-Path $root '.android-signing'
$store = Join-Path $private 'release.jks'
$properties = Join-Path $root 'android\keystore.properties'
if ((Test-Path -LiteralPath $store) -or (Test-Path -LiteralPath $properties)) {
    throw 'Signing files already exist. Reuse and back them up; do not replace the key used for published updates.'
}
New-Item -ItemType Directory -Path $private -Force | Out-Null
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$password = [Convert]::ToBase64String($bytes)
$env:MOVIEWATCHLIST_SIGNING_PASSWORD = $password
try {
    & $Keytool -genkeypair -keystore $store -storetype JKS -alias moviewatchlist -keyalg RSA -keysize 4096 -validity 10000 -dname 'CN=MyMovieList' -storepass:env MOVIEWATCHLIST_SIGNING_PASSWORD -keypass:env MOVIEWATCHLIST_SIGNING_PASSWORD
    if ($LASTEXITCODE -ne 0) { throw 'Signing key generation failed.' }
    @("storeFile=../.android-signing/release.jks", "storePassword=$password", 'keyAlias=moviewatchlist', "keyPassword=$password") | Set-Content -LiteralPath $properties -Encoding ascii
} finally {
    Remove-Item Env:MOVIEWATCHLIST_SIGNING_PASSWORD -ErrorAction SilentlyContinue
}
Write-Output 'Private Android signing files created. Back up .android-signing/release.jks and android/keystore.properties together, outside Git and release downloads.'
