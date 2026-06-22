[CmdletBinding()]
param(
  [string]$Version = "1.0.9"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DistDir = Join-Path $RepoRoot "dist"
$StageDir = Join-Path $DistDir "Kabuki-Cord-$Version-windows"
$ZipPath = Join-Path $DistDir "Kabuki-Cord-$Version-windows.zip"
$ExePath = Join-Path $RepoRoot "Install-Kabuki-Cord.exe"
$WrapperSource = Join-Path $ScriptDir "InstallWrapper.cs"
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$IconPath = Join-Path $RepoRoot "assets\app.ico"

if (-not (Test-Path $Csc)) {
  throw "Could not find csc.exe at $Csc"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
Remove-Item -Recurse -Force -Path $StageDir -ErrorAction SilentlyContinue
Remove-Item -Force -Path $ZipPath -ErrorAction SilentlyContinue
Remove-Item -Force -Path $ExePath -ErrorAction SilentlyContinue

$cscArgs = @(
  "/nologo",
  "/target:winexe",
  "/out:$ExePath",
  "/reference:System.Windows.Forms.dll"
)
if (Test-Path $IconPath) {
  $cscArgs += "/win32icon:$IconPath"
}
$cscArgs += $WrapperSource
& $Csc @cscArgs
if ($LASTEXITCODE -ne 0) {
  throw "Install wrapper build failed."
}

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

$excludeDirs = @(".git", ".venv", ".profiles", ".state", ".local", "dist", "__pycache__", "playwright-report", "test-results")
$excludeFiles = @(".env", "Install-Kabuki-Cord.exe")
$excludeSuffixes = @(".pyc", ".pyo")

Get-ChildItem -Path $RepoRoot -Force | ForEach-Object {
  if ($excludeDirs -contains $_.Name) { return }
  if ($excludeFiles -contains $_.Name) { return }
  $destination = Join-Path $StageDir $_.Name
  if ($_.PSIsContainer) {
    Copy-Item -Path $_.FullName -Destination $destination -Recurse -Force
  } elseif ($excludeSuffixes -notcontains $_.Extension) {
    Copy-Item -Path $_.FullName -Destination $destination -Force
  }
}

Get-ChildItem -Path $StageDir -Recurse -Force -Directory | Where-Object {
  $_.Name -in @("__pycache__") -or $_.Name.EndsWith(".egg-info")
} | Remove-Item -Recurse -Force

Copy-Item -Path $ExePath -Destination (Join-Path $StageDir "Install-Kabuki-Cord.exe") -Force

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
Write-Host $ZipPath
