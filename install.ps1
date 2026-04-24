# Oracle installer — Windows (PowerShell)
#
# Usage (from the cloned repo root):
#   .\install.ps1
#
# Usage (fresh machine, no clone yet):
#   irm https://raw.githubusercontent.com/<you>/oracle/main/install.ps1 | iex
#
# What it does:
#   1. Clones (or reuses) the Oracle repo at %USERPROFILE%\oracle
#   2. Creates a Python 3.12+ venv at <repo>\.venv
#   3. Installs Oracle in editable mode
#   4. Drops an `oracle.bat` launcher into %USERPROFILE%\bin
#   5. Adds %USERPROFILE%\bin to the user PATH (permanent)
#
# After this, `oracle` works in any new PowerShell / CMD window.

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "[oracle] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[oracle] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[oracle] $msg" -ForegroundColor Yellow }
function Die($msg)        { Write-Host "[oracle] $msg" -ForegroundColor Red; exit 1 }

# ---------- config ----------
$OracleHome     = if ($env:ORACLE_INSTALL_DIR) { $env:ORACLE_INSTALL_DIR } else { Join-Path $env:USERPROFILE "oracle" }
$OracleRepo     = if ($env:ORACLE_REPO_URL)    { $env:ORACLE_REPO_URL }    else { "" }
$BinDir         = Join-Path $env:USERPROFILE "bin"
$LauncherBat    = Join-Path $BinDir "oracle.bat"
$LauncherBash   = Join-Path $BinDir "oracle"

# ---------- 1. Python ----------
Write-Step "checking Python"
$python = $null
foreach ($candidate in @("python", "py -3.12", "py -3")) {
    try {
        $ver = & cmd /c "$candidate --version 2>&1"
        if ($LASTEXITCODE -eq 0 -and $ver -match "3\.(1[2-9]|[2-9]\d)") {
            $python = $candidate
            break
        }
    } catch {}
}
if (-not $python) { Die "Python 3.12+ not found. Install from https://python.org then re-run." }
Write-Ok "using Python: $python"

# ---------- 2. Clone or detect repo ----------
$localRepoGuess = if ($PSScriptRoot) { Join-Path $PSScriptRoot "pyproject.toml" } else { $null }
$repoIsHere = $localRepoGuess -and (Test-Path $localRepoGuess)
if ($repoIsHere) {
    $OracleHome = $PSScriptRoot
    Write-Ok "installing from local repo: $OracleHome"
} elseif (Test-Path (Join-Path $OracleHome ".git")) {
    Write-Step "repo already at $OracleHome — pulling"
    Push-Location $OracleHome
    git pull --ff-only
    Pop-Location
} else {
    if (-not $OracleRepo) {
        Die "Not inside an Oracle repo and \$env:ORACLE_REPO_URL not set. Either clone first or set the URL."
    }
    Write-Step "cloning $OracleRepo to $OracleHome"
    git clone $OracleRepo $OracleHome
}

# ---------- 3. venv + install ----------
$venv = Join-Path $OracleHome ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Step "creating venv at $venv"
    & cmd /c "$python -m venv `"$venv`""
    if ($LASTEXITCODE -ne 0) { Die "venv creation failed" }
}

Write-Step "installing dependencies (this can take a minute)"
& "$venvPy" -m pip install --upgrade pip | Out-Null
& "$venvPy" -m pip install -e "$OracleHome"
if ($LASTEXITCODE -ne 0) { Die "pip install failed" }

# ---------- 4. .env ----------
$envFile = Join-Path $OracleHome ".env"
$envExample = Join-Path $OracleHome ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Write-Step "creating .env from .env.example"
    Copy-Item $envExample $envFile
}

# ---------- 5. launcher ----------
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir | Out-Null }

$batBody = @"
@echo off
setlocal
set "ORACLE_ROOT=$OracleHome"
set "ORACLE_PY=%ORACLE_ROOT%\.venv\Scripts\python.exe"
if not exist "%ORACLE_PY%" (
  echo [oracle] venv missing — re-run install.ps1
  exit /b 1
)
"%ORACLE_PY%" -m oracle.cli %*
"@
Set-Content -Path $LauncherBat -Value $batBody -Encoding ASCII

# Bash wrapper too (Git Bash users)
$bashBody = @"
#!/usr/bin/env bash
ORACLE_PY="$($OracleHome -replace '\\', '/')/.venv/Scripts/python.exe"
if [ ! -x "`$ORACLE_PY" ]; then
  echo "[oracle] venv missing — re-run install.ps1" >&2
  exit 1
fi
exec "`$ORACLE_PY" -m oracle.cli "`$@"
"@
Set-Content -Path $LauncherBash -Value $bashBody -Encoding UTF8 -NoNewline
Write-Ok "launchers installed to $BinDir"

# ---------- 6. PATH ----------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" -contains $BinDir)) {
    Write-Step "adding $BinDir to user PATH"
    $new = if ([string]::IsNullOrEmpty($userPath)) { $BinDir } else { "$userPath;$BinDir" }
    [Environment]::SetEnvironmentVariable("Path", $new, "User")
    Write-Warn "open a NEW PowerShell/CMD window to pick up the PATH change"
} else {
    Write-Ok "PATH already contains $BinDir"
}

Write-Host ""
Write-Ok "oracle installed · home = $OracleHome"
Write-Host ""
Write-Host "next:" -ForegroundColor White
Write-Host "  1. open a new terminal"
Write-Host "  2. make sure Ollama is running  (https://ollama.com/download)"
Write-Host "  3. ollama pull qwen3:4b bge-m3"
Write-Host "  4. oracle doctor"
Write-Host "  5. oracle"
Write-Host ""
