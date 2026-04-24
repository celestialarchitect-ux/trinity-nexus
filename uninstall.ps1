# Oracle uninstaller — Windows
#
# Removes launchers + (optionally) the install dir. PATH entry stays — remove
# manually from System Properties if you want it gone.

param(
    [switch]$KeepData
)

$ErrorActionPreference = "Continue"

$BinDir      = Join-Path $env:USERPROFILE "bin"
$LauncherBat = Join-Path $BinDir "oracle.bat"
$LauncherBas = Join-Path $BinDir "oracle"
$OracleHome  = if ($env:ORACLE_INSTALL_DIR) { $env:ORACLE_INSTALL_DIR } else { Join-Path $env:USERPROFILE "oracle" }

foreach ($f in @($LauncherBat, $LauncherBas)) {
    if (Test-Path $f) { Remove-Item $f -Force; Write-Host "removed $f" }
}

if (-not $KeepData) {
    if (Test-Path $OracleHome) {
        Write-Host "removing install dir $OracleHome"
        Remove-Item -Recurse -Force $OracleHome
    }
} else {
    Write-Host "kept install dir $OracleHome (launchers removed)"
}

Write-Host "uninstall complete. restart your terminal."
