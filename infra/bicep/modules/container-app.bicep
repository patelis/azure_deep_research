targetScope = 'resourceGroup'

// Container Apps environment + the py-shiny app, running under the user-assigned managed
// identity (keyless to Azure OpenAI / Foundry / ACR). The `azd-service-name` tag lets
// `azd deploy` build the image, push it to ACR, and update this app. Session affinity is on so
// a browser reconnect lands on the same replica that holds the in-memory research task.

@description('Location for all resources.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive resource names.')
param environmentName string

@description('Resource id of the user-assigned managed identity.')
param userAssignedIdentityId string

@description('ACR login server for pulling the image.')
param acrLoginServer string

@description('Container image. Empty uses a placeholder until `azd deploy` pushes the real one.')
param containerImage string = ''

@description('Non-secret environment variables for the container (name/value objects).')
param env array = []

@description('Key Vault secret URI for the ACS connection string (empty to skip).')
param acsSecretUri string = ''

@description('Key Vault secret URI for the App Insights connection string (empty to skip).')
param appInsightsSecretUri string = ''

@description('azd service name (also the container name).')
param serviceName string = 'app'

@description('Minimum replicas. 0 scales to zero when idle; a Shiny WebSocket keeps a replica warm while a user is connected.')
param minReplicas int = 0

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)
var image = empty(containerImage) ? 'mcr.microsoft.com/k8se/quickstart:latest' : containerImage

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': serviceName })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        // Sticky sessions: keep a reconnecting browser on the replica holding its ExtendedTask.
        affinity: 'sticky'
      }
      registries: empty(acrLoginServer) ? [] : [
        {
          server: acrLoginServer
          identity: userAssignedIdentityId
        }
      ]
      // Secrets are Key Vault references resolved by the app's managed identity.
      secrets: concat(
        empty(acsSecretUri) ? [] : [
          {
            name: 'acs-connection-string'
            keyVaultUrl: acsSecretUri
            identity: userAssignedIdentityId
          }
        ],
        empty(appInsightsSecretUri) ? [] : [
          {
            name: 'appinsights-connection-string'
            keyVaultUrl: appInsightsSecretUri
            identity: userAssignedIdentityId
          }
        ]
      )
    }
    template: {
      containers: [
        {
          name: serviceName
          image: image
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat(
            env,
            empty(acsSecretUri) ? [] : [
              {
                name: 'ACS_CONNECTION_STRING'
                secretRef: 'acs-connection-string'
              }
            ],
            empty(appInsightsSecretUri) ? [] : [
              {
                name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
                secretRef: 'appinsights-connection-string'
              }
            ]
          )
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 3
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output name string = app.name
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
