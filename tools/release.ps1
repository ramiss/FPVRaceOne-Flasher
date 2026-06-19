# Cut a release of the FPVRaceOne Flasher.
#
# Creates a version tag (e.g. v1.0.0) and pushes it. Pushing a `v*` tag triggers
# .github/workflows/build.yml to build the .exe AND create a public GitHub
# Release with the .exe attached -- that's what your customers download.
#
# Run via the VSCode task "Release (tag & publish .exe)", or directly:
#     powershell -ExecutionPolicy Bypass -File tools/release.ps1 v1.0.0

param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Normalize: accept "1.0.0" or "v1.0.0", always tag as "v1.0.0".
$Version = $Version.Trim()
if ($Version -notmatch '^v') { $Version = "v$Version" }

# Make sure the current code is pushed before tagging it.
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Pushing latest commits on '$branch' first..." -ForegroundColor Cyan
git push origin $branch

Write-Host "Creating tag $Version ..." -ForegroundColor Cyan
git tag $Version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not create tag (does $Version already exist?)." -ForegroundColor Red
    exit 1
}

Write-Host "Pushing tag $Version ..." -ForegroundColor Cyan
git push origin $Version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tag push failed (see error above)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Release $Version triggered. The .exe will appear here when CI finishes:" -ForegroundColor Green
Write-Host "  https://github.com/ramiss/FPVRaceOne-Flasher/releases"
