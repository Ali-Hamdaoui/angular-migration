$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$launcherPath = Join-Path $repositoryRoot "scripts\dev-backend.ps1"
. $launcherPath

Describe "dev-backend live process-tree cleanup" {
    It "terminates a live launched parent and child process tree" {
        $pythonPath = Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe"
        $fixturePath = Join-Path $TestDrive "spawn_process_tree.py"
        $childPidPath = Join-Path $TestDrive "child.pid"
        @'
import pathlib
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
time.sleep(60)
'@ | Set-Content -LiteralPath $fixturePath -Encoding UTF8

        $rootProcess = Start-Process `
            -FilePath $pythonPath `
            -ArgumentList @($fixturePath, $childPidPath) `
            -NoNewWindow `
            -PassThru
        $childProcessId = $null
        try {
            $deadline = (Get-Date).AddSeconds(10)
            while (-not (Test-Path -LiteralPath $childPidPath) -and (Get-Date) -lt $deadline) {
                Start-Sleep -Milliseconds 100
            }
            (Test-Path -LiteralPath $childPidPath -PathType Leaf) | Should Be $true
            $childProcessId = [int](Get-Content -Raw -LiteralPath $childPidPath)

            Stop-BackendProcessTrees -Processes @($rootProcess)

            $remaining = @(
                Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                    Where-Object {
                        [int]$_.ProcessId -in @($rootProcess.Id, $childProcessId)
                    }
            )
            $remaining | Should BeNullOrEmpty
        }
        finally {
            Stop-Process -Id $rootProcess.Id -Force -ErrorAction SilentlyContinue
            if ($null -ne $childProcessId) {
                Stop-Process -Id $childProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
