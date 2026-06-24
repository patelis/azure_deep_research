targetScope = 'resourceGroup'

// Grounding with Bing Search resource + a project connection. This is the native Azure
// web-search path used by the researcher Foundry agent (managed, server-side). NOTE: the
// connection category/api-version occasionally change — adjust if a deployment rejects it.

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the resource name.')
param environmentName string

@description('Existing AI Foundry account name.')
param aiAccountName string

@description('Existing AI Foundry project name.')
param aiProjectName string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource bing 'Microsoft.Bing/accounts@2020-06-10' = {
  name: 'bing-${resourceToken}'
  location: 'global'
  tags: tags
  sku: { name: 'G1' }
  kind: 'Bing.Grounding'
}

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName

  resource project 'projects' existing = {
    name: aiProjectName
  }
}

resource bingConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: aiAccount::project
  name: 'bing-grounding-connection'
  properties: {
    category: 'GroundingWithBingSearch'
    target: 'https://api.bing.microsoft.com/'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: bing.listKeys().key1 }
    metadata: { type: 'bing_grounding', ApiType: 'Azure', ResourceId: bing.id }
  }
}

output connectionId string = bingConnection.id
output bingName string = bing.name
