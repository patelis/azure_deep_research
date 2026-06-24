targetScope = 'resourceGroup'

// Optional Azure Storage account + Table for the per-user API-key store (keyless via Entra ID).
// Used only when API_KEY_STORE=table. Grants Storage Table Data Contributor to the runtime
// identity (per-request lookup + durable daily counts) and the deployer (to seed/manage users).

@description('Location for the storage account.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the resource name.')
param environmentName string

@description('Principal id of the runtime managed identity.')
param runtimePrincipalId string

@description('Principal id of the deployer (to manage users).')
param deployerPrincipalId string

@allowed(['User', 'ServicePrincipal'])
param deployerPrincipalType string = 'User'

@description('Table name for the API-key store.')
param tableName string = 'apikeys'

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)
// Storage account names: 3-24 chars, lowercase alphanumerics only.
var storageName = toLower('st${take(replace(resourceToken, '-', ''), 22)}')
// Storage Table Data Contributor.
var tableContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
  }

  resource tableService 'tableServices@2023-05-01' = {
    name: 'default'

    resource table 'tables@2023-05-01' = {
      name: tableName
    }
  }
}

resource runtimeTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, runtimePrincipalId, tableContributorRoleId)
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableContributorRoleId)
  }
}

resource deployerTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, deployerPrincipalId, tableContributorRoleId)
  properties: {
    principalId: deployerPrincipalId
    principalType: deployerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableContributorRoleId)
  }
}

output tableEndpoint string = storage.properties.primaryEndpoints.table
output accountName string = storage.name
