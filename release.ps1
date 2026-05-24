# Release script for RM-Media-Decryptor
# Builds the executable using PyInstaller and uploads it to GitHub Releases using gh CLI.

$ErrorActionPreference = "Stop"

# Get current version from main.py
Write-Output "Extracting application version..."
$version = python -c "import main; print(main.APP_VERSION)"
if (-not $version) {
    Write-Error "Could not retrieve version from main.py."
}
Write-Output "Detected version: v$version"

# Run PyInstaller build
Write-Output "Building executable with PyInstaller..."
pyinstaller --clean RM_Media_Decryptor.spec

# Check if build output exists
$exePath = "dist/RM_Media_Decryptor.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build failed: $exePath not found."
}
Write-Output "Build succeeded: $exePath"

# Check if gh CLI is installed and authenticated
Write-Output "Verifying GitHub CLI (gh)..."
try {
    gh auth status
} catch {
    Write-Error "GitHub CLI is not installed or not authenticated. Please run 'gh auth login' first."
}

# Create GitHub Release
Write-Output "Creating GitHub Release v$version..."
gh release create "v$version" $exePath --title "v$version" --notes "Release v$version of RM-Media-Decryptor. Includes new features: key recovery, keyless PNG restoration, re-encryption, drag-and-drop, and legacy archive extraction."

Write-Output "Release successfully published to GitHub!"
