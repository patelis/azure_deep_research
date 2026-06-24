targetScope = 'resourceGroup'

// User-assigned managed identity for the deployed app (Container App). Its principal id
// receives the data-plane roles the human deployer gets, so DefaultAzureCredential works the
// same in the cloud as it does locally with `az login`.

@description('Location for the identity.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the resource name.')
param environmentName string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${resourceToken}'
  location: location
  tags: tags
}

output id string = uami.id
output name string = uami.name
output principalId string = uami.properties.principalId
output clientId string = uami.properties.clientId
