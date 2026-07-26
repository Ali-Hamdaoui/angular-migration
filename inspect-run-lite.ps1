param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$BackendUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$base = $BackendUrl.TrimEnd("/")

function Get-Api([string]$Path) {
    try {
        Invoke-RestMethod -Uri "$base$Path" -Method Get
    }
    catch {
        Write-Host "GET $Path failed: $($_.Exception.Message)" -ForegroundColor Yellow
        $null
    }
}

Write-Host "`n=== RUN STATE ===" -ForegroundColor Cyan
$state = Get-Api "/api/v1/runs/$RunId/state"
if ($state) {
    $state |
        Select-Object run_id, status, run_phase, phase_status,
            approval_status, state_version, updated_at |
        Format-List
}

Write-Host "`n=== LAST EVENTS ===" -ForegroundColor Cyan
$response = Get-Api "/api/v1/runs/$RunId/events"
$events = if ($response.events) { $response.events } else { $response }

if ($events) {
    $events |
        Select-Object -Last 20 |
        Select-Object sequence, event_type, occurred_at,
            @{Name="reason"; Expression={
                if ($_.reason) { $_.reason }
                elseif ($_.payload.reason) { $_.payload.reason }
                else { "" }
            }},
            @{Name="details"; Expression={
                $p = $_.payload
                $parts = @()
                foreach ($name in @(
                    "error_code",
                    "message",
                    "scanner",
                    "blocked_scanners",
                    "unknown_reasons",
                    "status"
                )) {
                    if ($null -ne $p.$name) {
                        $value = $p.$name
                        if ($value -is [System.Array]) {
                            $value = $value -join ", "
                        }
                        $parts += "${name}=$value"
                    }
                }
                $parts -join "; "
            }} |
        Format-Table -Wrap
}

Write-Host "`n=== DISCOVERY ===" -ForegroundColor Cyan
$discovery = Get-Api "/api/v1/runs/$RunId/discovery"
if ($discovery) {
    $discovery |
        Select-Object run_id, status, error_code, state_version, event_sequence |
        Format-List

    $rows = @()

    if ($discovery.scanners) {
        foreach ($property in $discovery.scanners.PSObject.Properties) {
            $value = $property.Value
            $rows += [pscustomobject]@{
                scanner = $property.Name
                status  = $value.status
                reasons = @($value.unknown_reasons + $value.blocking_reasons) -join ", "
            }
        }
    }
    elseif ($discovery.results) {
        foreach ($result in $discovery.results) {
            $rows += [pscustomobject]@{
                scanner = $result.scanner
                status  = $result.status
                reasons = @($result.unknown_reasons + $result.blocking_reasons) -join ", "
            }
        }
    }

    if ($rows.Count -gt 0) {
        $rows | Format-Table -AutoSize -Wrap
    }
    else {
        $discovery | ConvertTo-Json -Depth 20
    }
}

Write-Host "`n=== LLM ===" -ForegroundColor Cyan
$readiness = Get-Api "/api/v1/llm/readiness"
$activity = Get-Api "/api/v1/runs/$RunId/llm/activity"
$usage = Get-Api "/api/v1/runs/$RunId/usage"

if ($readiness) {
    $readiness |
        Select-Object status, provider, deployment_configured,
            model_capability, error_code |
        Format-List
}

Write-Host "Activity:"
if ($activity) { $activity | ConvertTo-Json -Depth 20 }

Write-Host "Usage:"
if ($usage) { $usage | ConvertTo-Json -Depth 20 }

Write-Host "`n=== VERDICT ===" -ForegroundColor Cyan
$types = @($events | ForEach-Object { $_.event_type })

if ($types -contains "DISCOVERY_BLOCKED") {
    Write-Host "Discovery blocked." -ForegroundColor Red
}
elseif ($types -contains "DISCOVERY_COMPLETED") {
    Write-Host "Discovery completed." -ForegroundColor Green
}
else {
    Write-Host "Discovery not completed yet." -ForegroundColor Yellow
}

if ($types -contains "ANALYSIS_AGENT_STARTED") {
    Write-Host "Analysis started." -ForegroundColor Green
}
else {
    Write-Host "Analysis did not start." -ForegroundColor Yellow
}
