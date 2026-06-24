targetScope = 'resourceGroup'

// Azure Communication Services + Email Communication Service with an Azure-managed domain
// (no DNS setup; ready immediately for low volume). The app emails the report via the ACS
// connection string (stored in Key Vault). From-address is donotreply@<auto>.azurecomm.net.

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive resource names.')
param environmentName string

@description('Data residency for ACS (e.g. "United States", "Europe").')
param dataLocation string = 'United States'

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)

resource emailService 'Microsoft.Communication/emailServices@2023-04-01' = {
  name: 'acsemail-${resourceToken}'
  location: 'global'
  tags: tags
  properties: {
    dataLocation: dataLocation
  }
}

resource managedDomain 'Microsoft.Communication/emailServices/domains@2023-04-01' = {
  parent: emailService
  name: 'AzureManagedDomain'
  location: 'global'
  tags: tags
  properties: {
    domainManagement: 'AzureManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communicationService 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: 'acs-${resourceToken}'
  location: 'global'
  tags: tags
  properties: {
    dataLocation: dataLocation
    linkedDomains: [
      managedDomain.id
    ]
  }
}

@description('ACS connection string (secret — store in Key Vault).')
output connectionString string = communicationService.listKeys().primaryConnectionString

@description('Default sender address on the Azure-managed domain.')
output senderAddress string = 'DoNotReply@${managedDomain.properties.fromSenderDomain}'
