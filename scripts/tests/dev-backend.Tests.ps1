$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$launcherPath = Join-Path $repositoryRoot "scripts\dev-backend.ps1"
$tokens = $null
$parseErrors = $null
$launcherAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $launcherPath,
    [ref]$tokens,
    [ref]$parseErrors
)
$hasGuardedEntryPoint = @(
    $launcherAst.FindAll(
        {
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq "Invoke-BackendDevelopmentRuntime"
        },
        $true
    )
).Count -eq 1
if ($hasGuardedEntryPoint) {
    . $launcherPath
}

Describe "dev-backend target root configuration" {
    It "creates, resolves, and exports the allowed target root" {
        $targetRoot = Join-Path $TestDrive "nested\target"

        $resolved = Initialize-BackendTargetRoot -TargetRoot $targetRoot

        (Test-Path -LiteralPath $targetRoot -PathType Container) | Should Be $true
        $resolved | Should Be (Resolve-Path -LiteralPath $targetRoot).Path
        $env:ALLOWED_TARGET_ROOTS | Should Be $resolved
    }
}

Describe "dev-backend child process specifications" {
    It "uses the repository virtual environment for the API and Transformer worker" {
        $backendRoot = Join-Path $repositoryRoot "backend"
        $python = Join-Path $backendRoot ".venv\Scripts\python.exe"

        $specifications = @(Get-BackendProcessSpecifications `
            -BackendRoot $backendRoot `
            -PythonPath $python `
            -Port 8123)

        $specifications.Count | Should Be 2
        $specifications[0].Name | Should Be "api"
        $specifications[0].FilePath | Should Be $python
        ($specifications[0].Arguments -join " ") |
            Should Be "-m uvicorn app.main:app --host 127.0.0.1 --port 8123 --reload"
        $specifications[1].Name | Should Be "transformer-worker"
        $specifications[1].FilePath | Should Be $python
        ($specifications[1].Arguments -join " ") |
            Should Be "-m app.orchestration.transformer_worker"
    }
}

Describe "dev-backend process-tree containment" {
    It "selects only launched process trees in leaf-first shutdown order" {
        $snapshot = @(
            [pscustomobject]@{ ProcessId = 100; ParentProcessId = 10 },
            [pscustomobject]@{ ProcessId = 101; ParentProcessId = 100 },
            [pscustomobject]@{ ProcessId = 102; ParentProcessId = 101 },
            [pscustomobject]@{ ProcessId = 200; ParentProcessId = 20 },
            [pscustomobject]@{ ProcessId = 201; ParentProcessId = 200 }
        )

        $selected = @(Get-ProcessTreeIds `
            -RootProcessIds @(100) `
            -ProcessSnapshot $snapshot)

        ($selected -join ",") | Should Be "102,101,100"
    }
}

Describe "two-command developer documentation" {
    It "documents the backend target-root parameter in the root README" {
        $content = Get-Content -Raw (Join-Path $repositoryRoot "README.md")

        $content | Should Match '\.\\scripts\\dev-backend\.ps1\s+`\s*\r?\n\s*-TargetRoot'
    }

    It "states that the backend launcher starts the Transformer worker" {
        $content = Get-Content -Raw (Join-Path $repositoryRoot "docs\developer-setup.md")

        $content | Should Match 'dev-backend\.ps1'
        $content | Should Match 'Transformer worker'
    }

    It "describes both supervised backend children in the scripts guide" {
        $content = Get-Content -Raw (Join-Path $repositoryRoot "scripts\README.md")

        $content | Should Match 'Uvicorn API'
        $content | Should Match 'Transformer worker'
    }
}
