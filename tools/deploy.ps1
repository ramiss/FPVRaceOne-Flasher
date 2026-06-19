# One-click deploy for the FPVRaceOne Flasher.
#
# Stages every change, commits it, and pushes to the `main` branch on GitHub.
# Pushing to `main` triggers .github/workflows/build.yml, which builds the .exe
# in the cloud and uploads it as a downloadable artifact.
#
# Normally run via the VSCode task "Deploy to GitHub" (Ctrl+Shift+B), but you
# can also run it directly:
#     powershell -ExecutionPolicy Bypass -File tools/deploy.ps1 "your message"

param(
    [Parameter(Mandatory = $true)]
    [string]$Message
)

# Always operate from the repo root (this script lives in tools/).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# CI only builds on `main`; rename the default branch on first run if needed.
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -eq 'master') {
    Write-Host "Renaming branch 'master' -> 'main' (CI builds on main)..." -ForegroundColor Yellow
    git branch -M main
    $branch = 'main'
}

Write-Host "Staging changes..." -ForegroundColor Cyan
git add -A

# git diff --cached --quiet exits 1 when something is staged, 0 when nothing is.
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Committing: $Message" -ForegroundColor Cyan
    git commit -m $Message
} else {
    Write-Host "No new changes to commit; pushing any existing commits." -ForegroundColor Yellow
}

Write-Host "Pushing to origin/$branch ..." -ForegroundColor Cyan
git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed (see error above)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Deployed. Watch the build here:" -ForegroundColor Green
Write-Host "  https://github.com/ramiss/FPVRaceOne-Flasher/actions"
