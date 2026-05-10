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
    Invoke-CheckStep "Backend focused tests" {
        docker compose -f docker/docker-compose.yml run --rm test python -m pytest -q tests/test_runs_router.py tests/test_eval_workflow.py
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

    Write-Host ""
    Write-Host "Fast checks passed."
} finally {
    Pop-Location
}
