$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $RepoRoot "frontend"

function Invoke-CheckStep {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [scriptblock] $Step
    )

    Write-Host ""
    Write-Host "==> $Name"
    & $Step
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Push-Location $RepoRoot
try {
    Invoke-CheckStep "Backend full test suite" {
        docker compose -f docker/docker-compose.yml run --rm test python -m pytest -q
    }

    Invoke-CheckStep "Frontend lint" {
        Push-Location $FrontendRoot
        try {
            pnpm lint
        } finally {
            Pop-Location
        }
    }

    Invoke-CheckStep "Frontend build" {
        Push-Location $FrontendRoot
        try {
            pnpm build
        } finally {
            Pop-Location
        }
    }

    Invoke-CheckStep "Frontend UI smoke" {
        Push-Location $FrontendRoot
        try {
            pnpm test:ui
        } finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "All checks passed."
} finally {
    Pop-Location
}
