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

    It "quiesces roots and rescans until no launched descendants remain" {
        $script:snapshotCallCount = 0
        $script:stoppedProcessIds = @()
        Mock Get-CimInstance {
            $script:snapshotCallCount++
            if ($script:snapshotCallCount -eq 1) {
                return @(
                    [pscustomobject]@{ ProcessId = 101; ParentProcessId = 100 },
                    [pscustomobject]@{ ProcessId = 102; ParentProcessId = 101 }
                )
            }
            if ($script:snapshotCallCount -eq 2) {
                # The intermediate process is gone, but its child still reports
                # the now-missing intermediate PID as its parent.
                return @(
                    [pscustomobject]@{ ProcessId = 102; ParentProcessId = 101 }
                )
            }
            return @()
        }
        Mock Stop-Process {
            param($Id)
            foreach ($stoppedId in @($Id)) {
                $script:stoppedProcessIds += [int]$stoppedId
            }
        }
        Mock Stop-WindowsProcessTree {}

        Stop-BackendProcessTrees -Processes @([pscustomobject]@{ Id = 100 })

        $script:snapshotCallCount | Should Be 13
        ($script:stoppedProcessIds[0..3] -join ",") | Should Be "100,102,101,102"
        Assert-MockCalled Stop-WindowsProcessTree -Times 1 -Exactly -ParameterFilter {
            $RootProcessId -eq 100
        }
    }
}

Describe "dev-backend partial startup cleanup" {
    It "stops the first child when the second child cannot start" {
        $script:startAttempt = 0
        Mock Start-Process {
            $script:startAttempt++
            if ($script:startAttempt -eq 1) {
                return [pscustomobject]@{ Id = 301 }
            }
            throw "second child failed"
        }
        Mock Stop-BackendProcessTrees {}
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

        { Start-BackendRuntimeProcesses -Specifications $specifications } |
            Should Throw "second child failed"
        Assert-MockCalled Stop-BackendProcessTrees -Times 1 -Exactly -ParameterFilter {
            $Processes.Count -eq 1 -and $Processes[0].Id -eq 301
        }
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
