[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Repo", "User")]
    [string]$Scope = "Repo"
)

$ErrorActionPreference = "Stop"

# Script location:
# <repo>\luna-desktop\backend\skills\img-to-html\scripts\install_codex.ps1
$imgSkillDir = Split-Path -Parent $PSScriptRoot
$skillRoot = Split-Path -Parent $imgSkillDir

$names = @("img-to-html", "to-wireframe", "openrouter-img")

foreach ($name in $names) {
    $source = Join-Path $skillRoot $name
    if (-not (Test-Path $source)) {
        throw "Required skill not found: $source"
    }
}

if ($Scope -eq "User") {
    $destinationRoot = Join-Path $HOME ".codex\skills"
}
else {
    $repoRoot = (& git -C $skillRoot rev-parse --show-toplevel).Trim()
    if (-not $repoRoot) {
        throw "Could not resolve git repository root."
    }
    $destinationRoot = Join-Path $repoRoot ".codex\skills"
}

if ($PSCmdlet.ShouldProcess($destinationRoot, "Create Codex skills directory")) {
    New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null
}

foreach ($name in $names) {
    $source = Join-Path $skillRoot $name
    $destination = Join-Path $destinationRoot $name

    if ($PSCmdlet.ShouldProcess($destination, "Install $name from $source")) {
        if (Test-Path $destination) {
            Remove-Item -Recurse -Force $destination
        }
        Copy-Item -Recurse -Force $source $destination
        Write-Host "Installed: $destination"
    }
}

Write-Host "Codex skill bundle ready at: $destinationRoot"
