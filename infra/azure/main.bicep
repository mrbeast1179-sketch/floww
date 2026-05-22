// infra/azure/main.bicep
// Azure production deployment for Floww / Confluence Decoder
// Uses: App Service (B1) + Container Registry + Key Vault + Cosmos DB + Monitor
//
// Prerequisites:
//   az login
//   az group create --name floww-prod-rg --location eastus
//   az deployment group create --resource-group floww-prod-rg \
//     --template-file infra/azure/main.bicep \
//     --parameters infra/azure/prod-params.json
//
// Cost estimate: ~$18/mo (B1 + ACR Basic) + Cosmos DB free tier (400 RU/s)

targetScope = 'resourceGroup'

// ── Parameters (from variables.bicep or inline) ──────────────────────────────

@description('Azure region')
param location string = resourceGroup().location

@description('Project name prefix')
param projectName string = 'floww'

@description('Environment')
param environment string = 'production'

@description('App Service Plan SKU')
param appServiceSku string = 'B1'

@description('App Service Plan tier')
param appServiceTier string = 'Basic'

@description('ACR SKU')
param acrSku string = 'Basic'

@description('Cosmos DB consistency')
param cosmosConsistency string = 'Session'

@description('VNet address space')
param vnetAddressSpace string = '10.0.0.0/16'

@description('Subnet prefix')
param subnetPrefix string = '10.0.1.0/24'

@secure()
param apiSecretKey string

@secure()
param wsApiToken string

@secure()
param dashSessionToken string

@secure()
param schwabClientId string = ''

@secure()
param schwabClientSecret string = ''

@secure()
param databentoApiKey string = ''

param alertEmail string = 'nav@example.com'

param monthlyBudgetUsd int = 50

param tags object = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
}

// ── Naming Convention ─────────────────────────────────────────────────────────

var appServicePlanName = '${projectName}-${environment}-plan'
var acrName = '${projectName}${environment}acr'  // ACR names: alphanumeric only, max 50
var cosmosName = '${projectName}-${environment}-cosmos'
var kvName = '${projectName}-${environment}-kv'
var appName = '${projectName}-${environment}-app'
var vnetName = '${projectName}-${environment}-vnet'
var subnetName = '${projectName}-${environment}-subnet'
var nsgName = '${projectName}-${environment}-nsg'
var monitorName = '${projectName}-${environment}-monitor'
var budgetName = '${projectName}-monthly-budget'

// ── VNet + Subnet + NSG ──────────────────────────────────────────────────────

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-https-inbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
          description: 'Allow HTTPS inbound'
        }
      }
      {
        name: 'allow-http-inbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
          description: 'Allow HTTP inbound'
        }
      }
      {
        name: 'deny-all-inbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
          description: 'Deny all other inbound'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressSpace
      ]
    }
    subnets: [
      {
        name: subnetName
        properties: {
          addressPrefix: subnetPrefix
          networkSecurityGroup: {
            id: nsg.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
          delegations: [
            {
              name: 'app-service-delegation'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
    ]
  }
}

resource subnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: vnet
  name: subnetName
  properties: {
    addressPrefix: subnetPrefix
    networkSecurityGroup: {
      id: nsg.id
    }
    privateEndpointNetworkPolicies: 'Disabled'
    delegations: [
      {
        name: 'app-service-delegation'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
}

// ── App Service Plan (B1) ─────────────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  sku: {
    name: appServiceSku
    tier: appServiceTier
    size: appServiceSku
    family: 'B'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true  // Linux
    perSiteScaling: false
  }
}

// ── Auto-scaling Rules ────────────────────────────────────────────────────────

resource autoScaleSettings 'Microsoft.Insights/autoscalesettings@2022-10-01' = {
  name: '${projectName}-autoscale'
  location: location
  tags: tags
  properties: {
    targetResourceUri: appServicePlan.id
    enabled: true
    profiles: [
      {
        name: 'default-profile'
        capacity: {
          minimum: '1'
          maximum: '2'
          default: '1'
        }
        rules: [
          {
            // Scale out: CPU > 70% for 5 min
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: appServicePlan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT5M'
              timeAggregation: 'Average'
              operator: 'GreaterThan'
              threshold: 70
            }
            scaleAction: {
              direction: 'Increase'
              type: 'ChangeCount'
              value: '1'
              cooldown: 'PT5M'
            }
          }
          {
            // Scale in: CPU < 30% for 10 min
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: appServicePlan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT10M'
              timeAggregation: 'Average'
              operator: 'LessThan'
              threshold: 30
            }
            scaleAction: {
              direction: 'Decrease'
              type: 'ChangeCount'
              value: '1'
              cooldown: 'PT10M'
            }
          }
          {
            // Scale out: Memory > 80% for 5 min
            metricTrigger: {
              metricName: 'MemoryPercentage'
              metricResourceUri: appServicePlan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT5M'
              timeAggregation: 'Average'
              operator: 'GreaterThan'
              threshold: 80
            }
            scaleAction: {
              direction: 'Increase'
              type: 'ChangeCount'
              value: '1'
              cooldown: 'PT5M'
            }
          }
        ]
      }
    ]
  }
}

// ── Azure Container Registry ──────────────────────────────────────────────────

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: acrSku
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
    // In production, disable public access and use private endpoint
  }
}

// ── Cosmos DB (Mongo API) ─────────────────────────────────────────────────────

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-09-15' = {
  name: cosmosName
  location: location
  tags: tags
  kind: 'MongoDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      {
        name: 'EnableMongo'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: cosmosConsistency
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableMongo'
      }
    ]
    apiProperties: {
      serverVersion: '4.2'
    }
  }
}

resource cosmosMongoDb 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases@2023-09-15' = {
  parent: cosmos
  name: 'confluence_decoder'
  location: location
  tags: tags
  properties: {
    resource: {
      id: 'confluence_decoder'
    }
    options: {
      throughput: 400
    }
  }
}

// Private endpoint for Cosmos DB
resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: '${projectName}-cosmos-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnet.id
    }
    privateLinkServiceConnections: [
      {
        name: '${projectName}-cosmos-pls'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: ['MongoDB']
        }
      }
    ]
  }
}

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true  // Use RBAC, not access policies
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: []
      virtualNetworkRules: [
        {
          id: subnet.id
          ignoreMissingVnetServiceEndpoint: false
        }
      ]
    }
  }
}

// Key Vault Secrets
resource secretMongoUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'mongo-url'
  properties: {
    value: cosmos.listConnectionStrings().connectionStrings[0].connectionString
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'api-secret-key'
  properties: {
    value: apiSecretKey
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretWsToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ws-api-token'
  properties: {
    value: wsApiToken
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretDashToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'dash-session-token'
  properties: {
    value: dashSessionToken
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretSchwabClientId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'schwab-client-id'
  properties: {
    value: empty(schwabClientId) ? 'placeholder-replace-via-cli' : schwabClientId
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretSchwabClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'schwab-client-secret'
  properties: {
    value: empty(schwabClientSecret) ? 'placeholder-replace-via-cli' : schwabClientSecret
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

resource secretDatabentoKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'databento-api-key'
  properties: {
    value: empty(databentoApiKey) ? 'placeholder-replace-via-cli' : databentoApiKey
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

// ── App Service (FastAPI) ─────────────────────────────────────────────────────

resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: appName
  location: location
  tags: tags
  kind: 'app,linux,container'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    virtualNetworkSubnetId: subnet.id
    siteConfig: {
      alwaysOn: true
      ftpsState: 'Disabled'
      http2Enabled: true
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      ipSecurityRestrictions: [
        {
          action: 'Allow'
          ipAddress: '0.0.0.0/0'
          name: 'allow-all-temp'
          priority: 100
          description: 'TODO: restrict to known IPs in production'
        }
      ]
      scmIpSecurityRestrictionsDefaultAction: 'Deny'
      ipSecurityRestrictionsDefaultAction: 'Deny'
      linuxFxVersion: 'DOCKER|${acr.properties.loginServer}/floww-backend:latest'
      appSettings: [
        {
          name: 'DOCKER_REGISTRY_SERVER_URL'
          value: 'https://${acr.properties.loginServer}'
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_USERNAME'
          value: acr.listCredentials().username
        }
        {
          name: 'DOCKER_REGISTRY_SERVER_PASSWORD'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'ENVIRONMENT'
          value: 'production'
        }
        {
          name: 'CORS_ORIGINS'
          value: 'https://${appName}.azurewebsites.net'
        }
        {
          name: 'MONGO_URL'
          value: '@Microsoft.KeyVault(SecretUri=${secretMongoUrl.properties.secretUri})'
        }
        {
          name: 'DB_NAME'
          value: 'confluence_decoder'
        }
        {
          name: 'API_SECRET_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${secretApiKey.properties.secretUri})'
        }
        {
          name: 'WS_API_TOKEN'
          value: '@Microsoft.KeyVault(SecretUri=${secretWsToken.properties.secretUri})'
        }
        {
          name: 'DASH_SESSION_TOKEN'
          value: '@Microsoft.KeyVault(SecretUri=${secretDashToken.properties.secretUri})'
        }
        {
          name: 'SCHWAB_CLIENT_ID'
          value: '@Microsoft.KeyVault(SecretUri=${secretSchwabClientId.properties.secretUri})'
        }
        {
          name: 'SCHWAB_CLIENT_SECRET'
          value: '@Microsoft.KeyVault(SecretUri=${secretSchwabClientSecret.properties.secretUri})'
        }
        {
          name: 'DATABENTO_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${secretDatabentoKey.properties.secretUri})'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
      ]
    }
    httpsOnly: true
  }
}

// RBAC: App Service -> Key Vault
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, appService.id, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')  // Key Vault Secrets User
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Azure Monitor ─────────────────────────────────────────────────────────────

resource monitor 'Microsoft.Insights/components@2020-02-02' = {
  name: monitorName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${projectName}-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Budget Alert ──────────────────────────────────────────────────────────────

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: monthlyBudgetUsd
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '${utcNow('yyyy-MM')}-01'
      endDate: '${int(utcNow('yyyy')) + 1}-12-31'
    }
    notifications: {
      Actual_GreaterThan_80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          alertEmail
        ]
      }
      Forecasted_GreaterThan_100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [
          alertEmail
        ]
      }
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output acrLoginServer string = acr.properties.loginServer
output keyVaultUri string = keyVault.properties.vaultUri
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output monitorInstrumentationKey string = monitor.properties.InstrumentationKey
output appServicePrincipalId string = appService.identity.principalId
