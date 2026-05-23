# Publish learning-portal to https://github.com/ankitsujanti-ux/GoogleColab
# Run from: learning-portal folder
#   .\publish.ps1

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/ankitsujanti-ux/GoogleColab.git"
$PublishDir = Join-Path $env:TEMP "GoogleColab-pages-publish"
$SourceDir = $PSScriptRoot
$LiveUrl = "https://ankitsujanti-ux.github.io/GoogleColab/"

$Exclude = @(".git", "publish.ps1", "DEPLOY.md")

Write-Host "Publishing from $SourceDir"

if (Test-Path $PublishDir) {
    Remove-Item -Recurse -Force $PublishDir
}

git clone $RepoUrl $PublishDir
Set-Location $PublishDir

Get-ChildItem -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force

Get-ChildItem $SourceDir -Force | Where-Object { $Exclude -notcontains $_.Name } | ForEach-Object {
    Copy-Item $_.FullName -Destination $PublishDir -Recurse -Force
}

git add -A
$status = git status --porcelain
if (-not $status) {
    Write-Host "No changes to publish."
    exit 0
}

git commit -m "Update learning portal"
git branch -M main

Write-Host "Pushing to GitHub..."
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Push failed. Sign in to GitHub, then run this script again." -ForegroundColor Yellow
    Write-Host "Use a Personal Access Token as the password (repo scope)."
    exit 1
}

Write-Host ""
Write-Host "Published. Wait about 1 minute, then open:"
Write-Host $LiveUrl -ForegroundColor Green
