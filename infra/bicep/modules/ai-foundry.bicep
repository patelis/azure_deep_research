targetScope = 'resourceGroup'

// Azure AI Foundry account (AIServices) + project + model deployments + data-plane RBAC.
// Keyless: local auth disabled, access granted via Entra ID. A custom Responsible AI
// content-filter policy is attached to the deployments (declarative model-layer guardrail).

@description('Location for all resources.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Environment name used to derive the account name.')
param environmentName string

@description('AI Foundry project name.')
param aiProjectName string

@description('Object id to grant data-plane roles.')
param principalId string

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('Optional runtime managed-identity principal id (granted the same inference roles).')
param runtimePrincipalId string = ''

@description('Model deployments to create on the account.')
param deployments deploymentType[]

@description('Attach a custom Responsible AI content-filter policy to the deployments.')
param enableCustomRaiPolicy bool = true

@description('Name of the custom RAI content-filter policy.')
param raiPolicyName string = 'deep-research-rai'

var resourceToken = uniqueString(subscription().id, resourceGroup().id, environmentName)
var accountName = 'aif-${resourceToken}'

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: aiProjectName
  parent: aiAccount
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    description: '${aiProjectName} deep research project'
    displayName: aiProjectName
  }
}

// Custom Responsible AI content-filter policy (declarative guardrail at the model layer).
resource raiPolicy 'Microsoft.CognitiveServices/accounts/raiPolicies@2024-10-01' = if (enableCustomRaiPolicy) {
  parent: aiAccount
  name: raiPolicyName
  properties: {
    basePolicyName: 'Microsoft.DefaultV2'
    mode: 'Default'
    contentFilters: [
      { name: 'Hate', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Hate', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Completion' }
      { name: 'Sexual', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Sexual', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Completion' }
      { name: 'Violence', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Violence', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Completion' }
      { name: 'Selfharm', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Selfharm', blocking: true, enabled: true, severityThreshold: 'Medium', source: 'Completion' }
      // Prompt Shield (jailbreak) at the model layer, in addition to the runtime check.
      { name: 'Jailbreak', blocking: true, enabled: true, source: 'Prompt' }
    ]
  }
}

// Deploy one model at a time to avoid capacity-allocation conflicts.
@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for deployment in deployments: {
    parent: aiAccount
    name: deployment.name
    sku: { name: deployment.sku.name, capacity: deployment.sku.capacity }
    properties: {
      model: {
        format: deployment.model.format
        name: deployment.model.name
        version: deployment.model.?version
      }
      raiPolicyName: enableCustomRaiPolicy ? raiPolicyName : null
    }
    dependsOn: [raiPolicy]
  }
]

// --- RBAC (data plane, keyless) ---
// Azure AI User.
resource userAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiAccount
  name: guid(aiAccount.id, principalId, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// Cognitive Services OpenAI User.
resource userOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiAccount
  name: guid(aiAccount.id, principalId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}

// Same inference roles for the runtime managed identity (deployed app).
resource runtimeAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(runtimePrincipalId)) {
  scope: aiAccount
  name: guid(aiAccount.id, runtimePrincipalId, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

resource runtimeOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(runtimePrincipalId)) {
  scope: aiAccount
  name: guid(aiAccount.id, runtimePrincipalId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}

output accountName string = aiAccount.name
output projectName string = project.name
output accountId string = aiAccount.id
output projectId string = project.id
output openAiEndpoint string = aiAccount.properties.endpoints['OpenAI Language Model Instance API']
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output contentSafetyEndpoint string = aiAccount.properties.endpoint
output deploymentNames array = [for d in deployments: d.name]

type deploymentType = {
  name: string
  model: {
    format: string
    name: string
    version: string?
  }
  sku: {
    name: string
    capacity: int
  }
}
