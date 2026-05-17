#!/bin/bash
# Azure deployment setup script for Confluence Decoder
# Run this once to create the Azure resources

RESOURCE_GROUP="confluence-decoder-rg"
LOCATION="eastus"
APP_NAME="confluence-decoder"
DB_NAME="confluence-db"

echo "=== Creating Azure Resource Group ==="
az group create --name $RESOURCE_GROUP --location $LOCATION

echo "=== Creating Azure App Service Plan (B1 tier - ~$13/month) ==="
az appservice plan create \
  --name "${APP_NAME}-plan" \
  --resource-group $RESOURCE_GROUP \
  --sku B1 \
  --is-linux

echo "=== Creating Azure Web App (Backend) ==="
az webapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --plan "${APP_NAME}-plan" \
  --runtime "PYTHON:3.11"

echo "=== Configuring Web App Settings ==="
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    MONGO_URL="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/mongo-url)" \
    DB_NAME="confluence_decoder" \
    DATABENTO_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/databento-key)" \
    POLYGON_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/polygon-key)" \
    ALPHA_VANTAGE_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/alphavantage-key)" \
    FINNHUB_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/finnhub-key)" \
    GEMINI_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/gemini-key)" \
    FLASHALPHA_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/flashalpha-key)" \
    MARKETSTACK_API_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/marketstack-key)" \
    API_SECRET_KEY="@Microsoft.KeyVault(SecretUri=https://confluence-kv.vault.azure.net/secrets/api-secret)" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
    WEBSITE_RUN_FROM_PACKAGE="1"

echo "=== Creating Azure Static Web App (Frontend) ==="
az staticwebapp create \
  --name "${APP_NAME}-frontend" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Free

echo "=== Creating Cosmos DB (MongoDB API) ==="
az cosmosdb create \
  --name $DB_NAME \
  --resource-group $RESOURCE_GROUP \
  --kind MongoDB \
  --server-version "4.2" \
  --default-consistency-level "Session" \
  --enable-free-tier true

echo "=== Getting connection strings ==="
echo "Web App Publish Profile:"
az webapp deployment list-publishing-profiles --name $APP_NAME --resource-group $RESOURCE_GROUP --xml

echo ""
echo "=== Setup complete! ==="
echo "Next steps:"
echo "1. Add the publish profile to GitHub Secrets as AZURE_WEBAPP_PUBLISH_PROFILE"
echo "2. Add the static web app token to GitHub Secrets as AZURE_STATIC_WEB_APPS_API_TOKEN"
echo "3. Add REACT_APP_BACKEND_URL to GitHub Secrets (e.g., https://confluence-decoder.azurewebsites.net)"
echo "4. Push to main branch to trigger deployment"