targetScope = 'resourceGroup'

// Azure Container Registry for the app image, with AcrPull granted to the runtime managed
// identity (keyless pull from the Container App).

@description('Location for the registry.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the resource name.')
param environmentName string

@description('Principal id of the runtime managed identity (granted AcrPull).')
param runtimePrincipalId string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: 'acr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, runtimePrincipalId, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
output id string = acr.id
