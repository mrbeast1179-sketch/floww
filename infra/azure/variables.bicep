// infra/azure/variables.bicep
// Configurable parameters for the Floww Azure deployment.
// Edit this file to change region, SKUs, or secret values — no need to touch main.bicep.

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Project name — used as prefix for all resources')
param projectName string = 'floww'

@description('Environment tag')
param environment string = 'production'

// ── App Service Plan ──────────────────────────────────────────────────────────

@description('App Service Plan SKU (B1=~$13/mo, B2=~$26/mo)')
param appServiceSku string = 'B1'

@description('App Service Plan tier')
param appServiceTier string = 'Basic'

// ── Container Registry ────────────────────────────────────────────────────────

@description('ACR SKU (Basic=~$5/mo, Standard)')
param acrSku string = 'Basic'

// ── Cosmos DB ─────────────────────────────────────────────────────────────────

@description('Cosmos DB consistency level')
param cosmosConsistency string = 'Session'

@description('Cosmos DB max RU/s (0 = serverless)')
param cosmosMaxRUs int = 400

// ── Networking ────────────────────────────────────────────────────────────────

@description('VNet address space')
param vnetAddressSpace string = '10.0.0.0/16'

@description('Subnet prefix')
param subnetPrefix string = '10.0.1.0/24'

// ── Secrets (passed at deploy time, never stored here) ─────────────────────────

@description('API secret key — pass at deploy time')
@secure()
param apiSecretKey string

@description('WebSocket API token — pass at deploy time')
@secure()
param wsApiToken string

@description('Dashboard session token — pass at deploy time')
@secure()
param dashSessionToken string

@description('Databento API key — pass at deploy time')
@secure()
param databentoApiKey string = ''

@description('Polygon.io API key — pass at deploy time')
@secure()
param polygonApiKey string = ''

@description('Alpha Vantage API key — pass at deploy time')
@secure()
param alphaVantageKey string = ''

@description('Alert email for budget notifications')
param alertEmail string = 'nav@example.com'

@description('Monthly budget in USD')
param monthlyBudgetUsd int = 50

// ── Tags ──────────────────────────────────────────────────────────────────────

param tags object = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
}
