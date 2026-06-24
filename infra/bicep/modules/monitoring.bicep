targetScope = 'resourceGroup'

// Log Analytics workspace + Application Insights, connected to the Foundry project so the app
// (and the Foundry portal's Tracing view) can collect OpenTelemetry traces.

@description('Location for all resources.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive resource names.')
param environmentName string

@description('Existing AI Foundry account name (parent of the project).')
param aiAccountName string

@description('Existing AI Foundry project name.')
param aiProjectName string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName

  resource project 'projects' existing = {
    name: aiProjectName
  }
}

// Connect Application Insights to the project (enables the Foundry Tracing experience).
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: aiAccount::project
  name: 'appinsights-connection'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: appInsights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsights.id }
  }
}

output connectionString string = appInsights.properties.ConnectionString
output appInsightsId string = appInsights.id
output logAnalyticsId string = logAnalytics.id
