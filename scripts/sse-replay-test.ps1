param([string]$BaseUrl = "http://127.0.0.1:8000", [string]$RunId = "mock-run-angular-18-to-21")
$ErrorActionPreference = "Stop"
$response = Invoke-WebRequest -Uri "$BaseUrl/migrations/$RunId/events?last_event_id=3" -Headers @{ Accept = "text/event-stream" } -UseBasicParsing -TimeoutSec 15
if ($response.Content -notmatch "id: 4") { throw "Expected replay to include event id 4." }
$response.Content