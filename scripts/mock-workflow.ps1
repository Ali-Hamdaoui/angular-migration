param([string]$BaseUrl = "http://127.0.0.1:8000")
$ErrorActionPreference = "Stop"
$preflight = Invoke-RestMethod -Method Post -Uri "$BaseUrl/migrations/preflight" -ContentType "application/json" -Body (@{
  source_path = $env:AMF_MOCK_SOURCE_PATH
  target_parent_path = $env:AMF_MOCK_TARGET_PARENT_PATH
  target_angular_family = "21.x"
  migration_mode = "strict-functional-parity"
  auto_approval_enabled = $false
} | ConvertTo-Json)
Invoke-RestMethod -Method Post -Uri "$BaseUrl/migrations/mock" -ContentType "application/json" -Body (@{ preflight_checksum = $preflight.checksum } | ConvertTo-Json)