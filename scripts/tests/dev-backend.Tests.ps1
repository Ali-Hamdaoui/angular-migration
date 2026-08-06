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

    It "rejects commas before creating a target root" {
        $targetRoot = Join-Path $TestDrive "unsafe,target"

        { Initialize-BackendTargetRoot -TargetRoot $targetRoot } |
            Should Throw "TargetRoot cannot contain a comma."
        (Test-Path -LiteralPath $targetRoot) | Should Be $false
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

Describe "dev-backend job-object containment" {
    It "ships the native Windows job helper" {
        $helperPath = Join-Path $repositoryRoot "scripts\BackendRuntimeJob.cs"

        (Test-Path -LiteralPath $helperPath -PathType Leaf) | Should Be $true
        (Get-Content -Raw -LiteralPath $helperPath) |
            Should Match 'JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE'
    }
}

Describe "dev-backend partial startup cleanup" {
    It "starts both children through the runtime job" {
        $runtimeJob = New-Object psobject
        $runtimeJob | Add-Member -MemberType ScriptMethod -Name StartProcess -Value {
            param($filePath, $arguments, $workingDirectory)
            return [pscustomobject]@{ Id = 300 + $arguments.Count }
        }
        $specifications = @(
            [pscustomobject]@{
                FilePath = "python.exe"
                Arguments = @("-m", "uvicorn")
                WorkingDirectory = $TestDrive
            },
            [pscustomobject]@{
                FilePath = "python.exe"
                Arguments = @("-m", "worker")
                WorkingDirectory = $TestDrive
            }
        )

        $processes = @(Start-BackendRuntimeProcesses `
            -Specifications $specifications `
            -RuntimeJob $runtimeJob)

        $processes.Count | Should Be 2
        $processes[0].Id | Should Be 302
        $processes[1].Id | Should Be 302
    }

    It "closes the runtime job when child startup fails" {
        $script:jobDisposed = $false
        $script:runtimeJob = New-Object psobject
        $script:runtimeJob | Add-Member -MemberType ScriptMethod -Name Dispose -Value {
            $script:jobDisposed = $true
        }
        Mock Invoke-BackendDatabaseMigration {}
        Mock New-BackendRuntimeJob { return $script:runtimeJob }
        Mock Start-BackendRuntimeProcesses { throw "second child failed" }

        { Invoke-BackendDevelopmentRuntime `
            -RepositoryRoot $repositoryRoot `
            -TargetRoot (Join-Path $TestDrive "target") `
            -Port 8123 } |
            Should Throw "second child failed"

        $script:jobDisposed | Should Be $true
    }
}

Describe "dev-backend child exit supervision" {
    It "reports the failed child name and exit code" {
        $apiProcess = [pscustomobject]@{ HasExited = $false; ExitCode = 0 }
        $apiProcess | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
        $workerProcess = [pscustomobject]@{ HasExited = $true; ExitCode = 7 }
        $workerProcess | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
        $specifications = @(
            [pscustomobject]@{ Name = "api" },
            [pscustomobject]@{ Name = "transformer-worker" }
        )

        { Assert-BackendRuntimeProcessesRunning `
            -Processes @($apiProcess, $workerProcess) `
            -Specifications $specifications } |
            Should Throw "transformer-worker exited with code 7."
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
