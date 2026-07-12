[CmdletBinding()]
param(
    [string]$Version = "2.5.0.dev0"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DistDir = Join-Path $RepoRoot "dist"
$StageDir = Join-Path $DistDir "Kabuki-Cord-$Version-windows"
$ZipPath = Join-Path $DistDir "Kabuki-Cord-$Version-windows.zip"
$ChecksumPath = "$ZipPath.sha256"
$ExePath = Join-Path $RepoRoot "Install-Kabuki-Cord.exe"
$WrapperSource = Join-Path $ScriptDir "InstallWrapper.cs"
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$IconPath = Join-Path $RepoRoot "src\nhi_zues\assets\app.ico"

if (-not (Test-Path $Csc)) {
  throw "Could not find csc.exe at $Csc"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
Remove-Item -Recurse -Force -Path $StageDir -ErrorAction SilentlyContinue
Remove-Item -Force -Path $ZipPath -ErrorAction SilentlyContinue
Remove-Item -Force -Path $ChecksumPath -ErrorAction SilentlyContinue
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

$SigningThumbprint = [Environment]::GetEnvironmentVariable("KABUKI_CORD_SIGNING_CERT_THUMBPRINT")
if ($SigningThumbprint) {
  $Certificate = Get-Item "Cert:\CurrentUser\My\$SigningThumbprint" -ErrorAction Stop
  $Signature = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $Certificate -TimestampServer "http://timestamp.digicert.com"
  if ($Signature.Status -ne "Valid") {
    throw "Installer signing failed: $($Signature.StatusMessage)"
  }
}

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

$ReleaseItems = @(
  "src",
  "installer",
  "pyproject.toml",
  "README.md",
  "SECURITY.md",
  "Install-Kabuki-Cord.cmd",
  "Run-Kabuki-Cord.cmd"
)

foreach ($Item in $ReleaseItems) {
  $Source = Join-Path $RepoRoot $Item
  if (-not (Test-Path $Source)) {
    throw "Required release item is missing: $Item"
  }
  Copy-Item -Path $Source -Destination (Join-Path $StageDir $Item) -Recurse -Force
}

Get-ChildItem -Path $StageDir -Recurse -Force -Directory | Where-Object {
  $_.Name -in @("__pycache__") -or $_.Name.EndsWith(".egg-info")
} | Remove-Item -Recurse -Force

Copy-Item -Path $ExePath -Destination (Join-Path $StageDir "Install-Kabuki-Cord.exe") -Force

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
$Hash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -Path $ChecksumPath -Value "$Hash *$(Split-Path -Leaf $ZipPath)" -Encoding Ascii
Write-Host $ZipPath
Write-Host $ChecksumPath
