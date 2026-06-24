targetScope = 'resourceGroup'

// Key Vault holding the app's runtime secrets (ACS connection string + App Insights connection
// string), surfaced to the Container App as Key Vault references resolved by its managed
// identity. RBAC-authorization mode.

@description('Location for the vault.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the vault name.')
param environmentName string

@description('Principal id of the runtime managed identity (granted secret read).')
param runtimePrincipalId string

@description('Principal id of the deployer (granted secret write to seed the values).')
param deployerPrincipalId string

@allowed(['User', 'ServicePrincipal'])
param deployerPrincipalType string = 'User'

@secure()
@description('ACS connection string to store (skipped if empty).')
param acsConnectionString string = ''

@secure()
@description('Application Insights connection string to store (skipped if empty).')
param appInsightsConnectionString string = ''

@description('Whether to create the ACS secret.')
param storeAcs bool

@description('Whether to create the App Insights secret.')
param storeAppInsights bool

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// Runtime identity: read secrets (Container App Key Vault references).
resource runtimeSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, runtimePrincipalId, '4633458b-17de-408a-b874-0445c86b69e6')
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// Deployer: write secrets to seed the values during deployment.
resource deployerSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, deployerPrincipalId, 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  properties: {
    principalId: deployerPrincipalId
    principalType: deployerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  }
}

resource acsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (storeAcs) {
  parent: vault
  name: 'acs-connection-string'
  properties: { value: acsConnectionString }
  dependsOn: [deployerSecretsOfficer]
}

resource appInsightsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (storeAppInsights) {
  parent: vault
  name: 'appinsights-connection-string'
  properties: { value: appInsightsConnectionString }
  dependsOn: [deployerSecretsOfficer]
}

output vaultName string = vault.name
output vaultUri string = vault.properties.vaultUri
// Versionless secret URIs (so rotation is picked up by the Container App).
output acsSecretUri string = storeAcs ? '${vault.properties.vaultUri}secrets/acs-connection-string' : ''
output appInsightsSecretUri string = storeAppInsights ? '${vault.properties.vaultUri}secrets/appinsights-connection-string' : ''
