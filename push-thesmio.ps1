# THESMIO publisher v0.1.1: launch from any working directory.
# Example: powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\push-thesmio.ps1
[CmdletBinding()]
param(
  [string]$SourcePath = '',
  [string]$Repo = 'https://github.com/Donacgreece/thesmio.git',
  [switch]$SkipPush
)
$ErrorActionPreference = 'Stop'
$startingDirectory = (Get-Location).Path
function Is-Project([string]$path) {
  return $path -and (Test-Path -LiteralPath (Join-Path $path 'package.json')) -and (Test-Path -LiteralPath (Join-Path $path 'src\App.tsx')) -and (Test-Path -LiteralPath (Join-Path $path '.github\workflows\pages.yml'))
}
function Find-Project {
  if ($SourcePath) {
    $resolved = (Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop).Path
    if (-not (Is-Project $resolved)) { throw "Not a THESMIO project folder: $resolved" }
    return $resolved
  }
  $scriptDirectory = Split-Path -Parent $MyInvocation.PSCommandPath
  # Using $PSScriptRoot directly is reliable even inside nested functions.
  $roots = @($PSScriptRoot, $startingDirectory, (Join-Path $env:USERPROFILE 'Downloads')) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
  foreach ($root in $roots) { if (Is-Project $root) { return $root } }
  $matches = @()
  foreach ($root in $roots) {
    # Only project-like directories; no need to recursively inspect node_modules.
    $dirs = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)
    foreach ($dir in $dirs) {
      if ($dir.Name -in @('node_modules','.git','dist')) { continue }
      if (Is-Project $dir.FullName) { $matches += $dir }
      if ($root -like '*Downloads*') {
        foreach ($nested in @(Get-ChildItem -LiteralPath $dir.FullName -Directory -ErrorAction SilentlyContinue)) {
          if (Is-Project $nested.FullName) { $matches += $nested }
        }
      }
    }
  }
  if (-not $matches) { throw 'THESMIO files not found. Extract ZIP into Downloads or specify -SourcePath "C:\path\to\THESMIO".' }
  $chosen = $matches | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  Write-Host "Automatically found: $($chosen.FullName)" -ForegroundColor Cyan
  return $chosen.FullName
}
function Assert-LastExit([string]$message) { if ($LASTEXITCODE -ne 0) { throw $message } }
try {
  Write-Host 'THESMIO v0.4.0 | GitHub publisher' -ForegroundColor Cyan
  foreach ($tool in @('git','node','npm')) { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found. Install Git for Windows and Node.js LTS." } }
  $source = Find-Project
  Push-Location $source
  try {
    & npm.cmd install --no-audit --no-fund
    Assert-LastExit 'npm install failed.'
    & npm.cmd run check
    Assert-LastExit 'TypeScript check failed. Nothing was pushed.'
    & npm.cmd run build
    Assert-LastExit 'Production build failed. Nothing was pushed.'
  } finally { Pop-Location }
  if ($SkipPush) { Write-Host 'Local validation completed. Push skipped.' -ForegroundColor Green; return }
  $target = Join-Path $env:TEMP 'thesmio-publish-checkout'
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
  & git clone $Repo $target
  Assert-LastExit 'Clone failed. Check GitHub permissions.'
  Push-Location $target
  try {
    & git checkout -B main
    Assert-LastExit 'Checkout main failed.'
    $exclusions = @('.git','node_modules','dist','.env','.env.local')
    Get-ChildItem -LiteralPath $source -Force | Where-Object { $exclusions -notcontains $_.Name } | ForEach-Object {
      $destination = Join-Path $target $_.Name
      if ($_.Name -eq 'public') {
        $existingData = Join-Path $target 'public\data\catalog.json'
        if ((Test-Path -LiteralPath $existingData) -and (Test-Path -LiteralPath (Join-Path $source 'public\data\catalog.json'))) {
          $backupData = Join-Path $env:TEMP 'thesmio-existing-catalog.json'
          Copy-Item -LiteralPath $existingData -Destination $backupData -Force
        }
      }
      if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }
      Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }
    if ($backupData -and (Test-Path -LiteralPath $backupData)) {
      $newData = Join-Path $target 'public\data\catalog.json'
      Copy-Item -LiteralPath $backupData -Destination $newData -Force
      Remove-Item -LiteralPath $backupData -Force
    }
    & git add --all
    Assert-LastExit 'Git staging failed.'
    if (@(& git status --porcelain).Count -gt 0) {
      & git -c user.name='THESMIO Publisher' -c user.email='thesmio-publisher@users.noreply.github.com' commit -m 'Publish THESMIO v0.4.0'
      Assert-LastExit 'Git commit failed.'
    }
    & git push -u origin main
    Assert-LastExit 'Git push failed.'
    Write-Host 'Source pushed successfully. Check the GitHub Actions deployment.' -ForegroundColor Green
    Write-Host 'https://github.com/Donacgreece/thesmio/actions'
    Write-Host 'https://donacgreece.github.io/thesmio/'
  } finally { Pop-Location }
} finally { Set-Location $startingDirectory }
