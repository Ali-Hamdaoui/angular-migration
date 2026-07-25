param([switch]$Smoke)

$endpoint = $env:AZURE_OPENAI_ENDPOINT
$uri = if ($endpoint) { [Uri]$endpoint } else { $null }
[ordered]@{
  LLM_ENABLED = [bool]($env:LLM_ENABLED -and $env:LLM_ENABLED -notin @('0','false','False'))
  resolved_endpoint_hostname = if ($uri) { $uri.Host } else { $null }
  resolved_deployment_alias = if ($env:AZURE_OPENAI_DEPLOYMENT) { $env:AZURE_OPENAI_DEPLOYMENT } else { $null }
  authentication_mode = if ($env:AZURE_OPENAI_API_KEY) { 'api_key' } else { 'missing' }
  responses_endpoint_path = '/openai/v1/responses'
  schema_registry_version = $env:LLM_SCHEMA_REGISTRY_VERSION
  prompt_version = 'analysis_agent_v1 / analysis_reviewer_v1'
  timeout_seconds = $env:LLM_TIMEOUT_SECONDS
  retry_policy = $env:LLM_MAX_TRANSPORT_RETRIES
  token_budget = $env:LLM_TOKEN_BUDGET
  cost_budget = $env:LLM_COST_BUDGET_USD
} | ConvertTo-Json

if ($Smoke) {
  Write-Output 'Smoke request is operator-triggered through POST /api/v1/llm/smoke; no request was issued by this diagnostic-only command.'
}
