targetScope = 'subscription'

// =============================================================================
// Azure-native deep research app (simplified) — top-level infrastructure.
// Provisions: resource group, a user-assigned managed identity, an AI Foundry account +
// project, main + mini chat deployments (with a custom RAI policy), Log Analytics +
// Application Insights, Grounding with Bing, Azure Communication Services (email), Key Vault,
// optionally a Table-Storage key store, a budget, and a Container Apps environment + the
// py-shiny app. Keyless throughout (Entra ID). Foundry AGENTS are created/updated separately
// by utils/sync_agents.py (no ARM resource type for agents) — the app resolves them by name.
// =============================================================================

@minLength(1)
@maxLength(64)
@description('Environment name, used to derive resource names.')
param environmentName string

@description('Resource group to create/use.')
param resourceGroupName string = 'rg-${environmentName}'

// Regions where the Azure OpenAI Responses API AND Grounding with Bing are available.
@allowed([
  'eastus'
  'eastus2'
  'francecentral'
  'japaneast'
  'norwayeast'
  'swedencentral'
  'switzerlandnorth'
  'westus'
  'westus3'
])
@description('Primary location for all resources.')
param location string = 'swedencentral'

@description('Object id of the user/service principal to grant data-plane roles.')
param principalId string

@allowed(['User', 'ServicePrincipal'])
@description('Principal type for role assignments.')
param principalType string = 'User'

@description('AI Foundry project name.')
param aiProjectName string = 'proj-${environmentName}'

@description('Azure OpenAI API version (must support the Responses API).')
param azureOpenAiApiVersion string = '2025-03-01-preview'

// --- Model deployments (override to the latest GPT series available in-region) ---
param mainModel string = 'gpt-4.1'
param mainModelVersion string = ''
param mainModelCapacity int = 20

param miniModel string = 'gpt-4.1-mini'
param miniModelVersion string = ''
param miniModelCapacity int = 50

@description('Provision Log Analytics + Application Insights and wire it to the project.')
param enableMonitoring bool = true

@description('Provision a monthly cost budget with email alerts.')
param enableBudget bool = true
param budgetAmount int = 20
param budgetAlertEmails array = []
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Container image for the app (empty = placeholder until `azd deploy` pushes it).')
param containerImage string = ''

@description('Allowed access keys as name:sha256hash, comma-separated (empty = gate disabled).')
param apiKeys string = ''

@description('Per-key daily cap on research runs (cost guard).')
param maxRunsPerKeyPerDay int = 3

@description('Use a Table Storage key store (per-request lookup + durable counts) instead of the API_KEYS env list.')
param enableApiKeyTable bool = false

// --- Orchestration caps (cost guards) ---
param maxSubagentsPerRun int = 5
param maxParallelResearchers int = 3
param maxDelegationRounds int = 3
param subagentsPerRound int = 3
param maxSearchesPerResearcher int = 5
param researcherMaxCompletionTokens int = 0
param maxClarifyRounds int = 3

var tags = { 'azd-env-name': environmentName }

var deployments = [
  {
    name: mainModel
    model: { format: 'OpenAI', name: mainModel, version: empty(mainModelVersion) ? null : mainModelVersion }
    sku: { name: 'GlobalStandard', capacity: mainModelCapacity }
  }
  {
    name: miniModel
    model: { format: 'OpenAI', name: miniModel, version: empty(miniModelVersion) ? null : miniModelVersion }
    sku: { name: 'GlobalStandard', capacity: miniModelCapacity }
  }
]

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  scope: rg
  name: 'identity'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
  }
}

module foundry 'modules/ai-foundry.bicep' = {
  scope: rg
  name: 'ai-foundry'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    aiProjectName: aiProjectName
    principalId: principalId
    principalType: principalType
    runtimePrincipalId: identity.outputs.principalId
    deployments: deployments
  }
}

module monitoring 'modules/monitoring.bicep' = if (enableMonitoring) {
  scope: rg
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    aiAccountName: foundry.outputs.accountName
    aiProjectName: foundry.outputs.projectName
  }
}

// Grounding with Bing for the researcher agent (always on — the researcher requires it).
module bing 'modules/bing-grounding.bicep' = {
  scope: rg
  name: 'bing-grounding'
  params: {
    tags: tags
    environmentName: environmentName
    aiAccountName: foundry.outputs.accountName
    aiProjectName: foundry.outputs.projectName
  }
}

// Azure Communication Services email (report delivery).
module communication 'modules/communication.bicep' = {
  scope: rg
  name: 'communication'
  params: {
    tags: tags
    environmentName: environmentName
  }
}

module budget 'modules/budget.bicep' = if (enableBudget && !empty(budgetAlertEmails)) {
  scope: rg
  name: 'budget'
  params: {
    amount: budgetAmount
    startDate: budgetStartDate
    contactEmails: budgetAlertEmails
  }
}

module registry 'modules/registry.bicep' = {
  scope: rg
  name: 'registry'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    runtimePrincipalId: identity.outputs.principalId
  }
}

// Optional Table Storage backing the per-user key store (keyless).
module keyStore 'modules/storage.bicep' = if (enableApiKeyTable) {
  scope: rg
  name: 'key-store'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    runtimePrincipalId: identity.outputs.principalId
    deployerPrincipalId: principalId
    deployerPrincipalType: principalType
  }
}

// Key Vault for runtime secrets (ACS + App Insights connection strings).
module keyVault 'modules/key-vault.bicep' = {
  scope: rg
  name: 'key-vault'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    runtimePrincipalId: identity.outputs.principalId
    deployerPrincipalId: principalId
    deployerPrincipalType: principalType
    storeAcs: true
    storeAppInsights: enableMonitoring
    acsConnectionString: communication.outputs.connectionString
    appInsightsConnectionString: enableMonitoring ? monitoring!.outputs.connectionString : ''
  }
}

// Connection strings are injected as Key Vault-referenced secrets by the container-app module.
var containerEnv = [
  { name: 'AZURE_OPENAI_ENDPOINT', value: foundry.outputs.openAiEndpoint }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
  { name: 'MAIN_MODEL', value: mainModel }
  { name: 'MINI_MODEL', value: miniModel }
  { name: 'AZURE_AI_PROJECT_ENDPOINT', value: foundry.outputs.projectEndpoint }
  { name: 'AZURE_CONTENT_SAFETY_ENDPOINT', value: foundry.outputs.contentSafetyEndpoint }
  { name: 'BING_CONNECTION_ID', value: bing.outputs.connectionId }
  { name: 'DEEP_RESEARCH_PROMPTS_DIR', value: '/app/backend/prompts' }
  { name: 'ENABLE_CONTENT_SAFETY', value: 'true' }
  { name: 'TRACE_CONTENT', value: 'false' }
  { name: 'ACS_SENDER_ADDRESS', value: communication.outputs.senderAddress }
  { name: 'API_KEYS', value: apiKeys }
  { name: 'API_KEY_STORE', value: enableApiKeyTable ? 'table' : 'env' }
  { name: 'AZURE_TABLE_ENDPOINT', value: enableApiKeyTable ? keyStore!.outputs.tableEndpoint : '' }
  { name: 'MAX_RUNS_PER_KEY_PER_DAY', value: string(maxRunsPerKeyPerDay) }
  { name: 'MAX_SUBAGENTS_PER_RUN', value: string(maxSubagentsPerRun) }
  { name: 'MAX_PARALLEL_RESEARCHERS', value: string(maxParallelResearchers) }
  { name: 'MAX_DELEGATION_ROUNDS', value: string(maxDelegationRounds) }
  { name: 'SUBAGENTS_PER_ROUND', value: string(subagentsPerRound) }
  { name: 'MAX_SEARCHES_PER_RESEARCHER', value: string(maxSearchesPerResearcher) }
  { name: 'RESEARCHER_MAX_COMPLETION_TOKENS', value: string(researcherMaxCompletionTokens) }
  { name: 'MAX_CLARIFY_ROUNDS', value: string(maxClarifyRounds) }
  // AZURE_CLIENT_ID disambiguates the user-assigned identity for DefaultAzureCredential.
  { name: 'AZURE_CLIENT_ID', value: identity.outputs.clientId }
]

module containerApp 'modules/container-app.bicep' = {
  scope: rg
  name: 'container-app'
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    userAssignedIdentityId: identity.outputs.id
    acrLoginServer: registry.outputs.loginServer
    containerImage: containerImage
    env: containerEnv
    acsSecretUri: keyVault.outputs.acsSecretUri
    appInsightsSecretUri: keyVault.outputs.appInsightsSecretUri
  }
}

// --- Outputs (populate .env from these: `azd env get-values > .env`) ---
output AZURE_RESOURCE_GROUP string = resourceGroupName
output AZURE_OPENAI_ENDPOINT string = foundry.outputs.openAiEndpoint
output AZURE_OPENAI_API_VERSION string = azureOpenAiApiVersion
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_CONTENT_SAFETY_ENDPOINT string = foundry.outputs.contentSafetyEndpoint
output MAIN_MODEL string = mainModel
output MINI_MODEL string = miniModel
output BING_CONNECTION_ID string = bing.outputs.connectionId
output APPLICATIONINSIGHTS_CONNECTION_STRING string = enableMonitoring ? monitoring!.outputs.connectionString : ''
output ACS_SENDER_ADDRESS string = communication.outputs.senderAddress
output AZURE_CLIENT_ID string = identity.outputs.clientId
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.vaultName
output AZURE_TABLE_ENDPOINT string = enableApiKeyTable ? keyStore!.outputs.tableEndpoint : ''
output SERVICE_APP_URI string = containerApp.outputs.uri
