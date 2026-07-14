[CmdletBinding()]
param(
  [switch]$NoLaunch,
  [switch]$NoShortcuts
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $RepoRoot

$DataDir = Join-Path $env:LOCALAPPDATA "Kabuki-Cord"
$StateDir = Join-Path $DataDir "state"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$LogPath = Join-Path $StateDir "install.log"

try {
  Start-Transcript -Path $LogPath -Append | Out-Null
} catch {
  Write-Warning "Could not start transcript: $($_.Exception.Message)"
}

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-CommandExists {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-PythonCandidate {
  param(
    [string]$Exe,
    [string[]]$BaseArgs
  )
  try {
    $args = @($BaseArgs) + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")
    & $Exe @args | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return @{ Exe = $Exe; Args = $BaseArgs }
    }
  } catch {
    return $null
  }
  return $null
}

function Find-Python {
  $candidates = @(
    @{ Exe = "py"; Args = @("-3.13") },
    @{ Exe = "py"; Args = @("-3.12") },
    @{ Exe = "py"; Args = @("-3.11") },
    @{ Exe = "python"; Args = @() }
  )

  foreach ($candidate in $candidates) {
    $found = Test-PythonCandidate -Exe $candidate.Exe -BaseArgs $candidate.Args
    if ($found) { return $found }
  }

  return $null
}

function Invoke-BasePython {
  param(
    [hashtable]$Python,
    [string[]]$Arguments
  )
  $allArgs = @($Python.Args) + $Arguments
  & $Python.Exe @allArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Python command failed: $($Python.Exe) $($allArgs -join ' ')"
  }
}

function Set-EnvValue {
  param(
    [string]$Path,
    [string]$Name,
    [string]$Value
  )
  $lines = @()
  if (Test-Path $Path) {
    $lines = Get-Content $Path
  }
  $found = $false
  $updated = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($Name))=") {
      $found = $true
      "$Name=$Value"
    } else {
      $line
    }
  }
  if (-not $found) {
    $updated += "$Name=$Value"
  }
  Set-Content -Path $Path -Value $updated -Encoding UTF8
}

function Test-ChromeInstalled {
  $paths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
  )
  foreach ($path in $paths) {
    if ($path -and (Test-Path $path)) { return $true }
  }
  return $false
}

function New-Shortcut {
  param(
    [string]$ShortcutPath,
    [string]$TargetPath,
    [string]$WorkingDirectory,
    [string]$Description
  )
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($ShortcutPath)
  $shortcut.TargetPath = $TargetPath
  $shortcut.WorkingDirectory = $WorkingDirectory
  $shortcut.Description = $Description
  $iconPath = Join-Path $WorkingDirectory "src\nhi_zues\assets\app.ico"
  if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
  } else {
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
  }
  $shortcut.Save()
}

try {
  Write-Step "Preparing Kabuki-Cord install in $RepoRoot"
  New-Item -ItemType Directory -Force -Path $DataDir, $StateDir | Out-Null

  if (-not (Test-ChromeInstalled)) {
    Write-Step "Chrome was not detected; configuring Playwright Chromium fallback"
    Set-EnvValue -Path (Join-Path $DataDir "settings.env") -Name "NHI_ZUES_BROWSER_CHANNEL" -Value ""
  }

  Write-Step "Checking Python 3.11+"
  $python = Find-Python
  if (-not $python) {
    if (Test-CommandExists "winget") {
      Write-Step "Python 3.11+ was not found; installing Python 3.13 with winget"
      winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
      $python = Find-Python
    }
  }
  if (-not $python) {
    Start-Process "https://www.python.org/downloads/windows/"
    throw "Python 3.11+ is required and could not be installed automatically. Install Python, then run this installer again."
  }

  Write-Step "Creating virtual environment"
  if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-BasePython -Python $python -Arguments @("-m", "venv", ".venv")
  }

  $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
  Write-Step "Installing Kabuki-Cord dependencies"
  & $venvPython -m pip install --upgrade pip setuptools wheel
  if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
  & $venvPython -m pip install -e .
  if ($LASTEXITCODE -ne 0) { throw "Kabuki-Cord package install failed." }

  Write-Step "Installing Playwright browser support"
  & $venvPython -m playwright install chromium
  if ($LASTEXITCODE -ne 0) { throw "Playwright browser install failed." }

  if (-not $NoShortcuts) {
    Write-Step "Creating shortcuts"
    $desktopExe = Join-Path $RepoRoot ".venv\Scripts\kabuki-cord-desktop.exe"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $programs = [Environment]::GetFolderPath("Programs")
    $startMenuDir = Join-Path $programs "Kabuki-Cord"
    New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
    New-Shortcut -ShortcutPath (Join-Path $desktop "Kabuki-Cord.lnk") -TargetPath $desktopExe -WorkingDirectory $RepoRoot -Description "Launch Kabuki-Cord"
    New-Shortcut -ShortcutPath (Join-Path $startMenuDir "Kabuki-Cord.lnk") -TargetPath $desktopExe -WorkingDirectory $RepoRoot -Description "Launch Kabuki-Cord"
  }

  Write-Step "Install complete"
  Write-Host "Launch from the Desktop shortcut, Start Menu, or Run-Kabuki-Cord.cmd." -ForegroundColor Green

  if (-not $NoLaunch) {
    Write-Step "Launching Kabuki-Cord"
    Start-Process -FilePath (Join-Path $RepoRoot ".venv\Scripts\kabuki-cord-desktop.exe") -WorkingDirectory $RepoRoot
  }
} finally {
  try {
    Stop-Transcript | Out-Null
  } catch {
  }
}
