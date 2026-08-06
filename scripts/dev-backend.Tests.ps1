$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherPath = Join-Path $repoRoot "scripts\dev-backend.ps1"

Describe "dev-backend launcher" {
    BeforeAll {
        $scriptText = Get-Content -Raw -LiteralPath $launcherPath
    }

    It "accepts the requested target root and port parameters" {
        $scriptText | Should Match '\[string\]\$TargetRoot\s*=\s*"C:\\Users\\hamdaoui\.ali\\Downloads\\MSA-COMMON-STG1"'
        $scriptText | Should Match '\[ValidateRange\(1,\s*65535\)\]\s*\[int\]\$Port\s*=\s*8000'
    }

    It "starts the Transformer worker with the same Python executable as Uvicorn" {
        $scriptText | Should Match '\$transformerArguments\s*=|app\.orchestration\.transformer_worker'
        $scriptText | Should Match 'Start-Process'
        $scriptText | Should Match '\$python'
    }

    It "configures the target root before starting child processes" {
        $environmentIndex = $scriptText.IndexOf('$env:ALLOWED_TARGET_ROOTS')
        $startProcessIndex = $scriptText.IndexOf('Start-Process')

        $environmentIndex | Should BeGreaterThan -1
        $startProcessIndex | Should BeGreaterThan -1
        $environmentIndex | Should BeLessThan $startProcessIndex
    }

    It "cleans up child process trees in a finally block" {
        $scriptText | Should Match 'function\s+Stop-ProcessTree'
        $scriptText | Should Match 'finally\s*\{'
        $scriptText | Should Match 'Stop-ProcessTree'
    }

    It "parses as valid PowerShell" {
        $tokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            $launcherPath,
            [ref]$tokens,
            [ref]$parseErrors
        ) | Out-Null

        $parseErrors | Should BeNullOrEmpty
    }
}
