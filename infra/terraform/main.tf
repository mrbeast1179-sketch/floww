# infra/terraform/main.tf
# Azure production deployment for Floww / Confluence Decoder
# Uses Azure App Service (B1) + Cosmos DB (Mongo API) + Key Vault + ACR
#
# Prerequisites:
#   az login
#   terraform init
#   terraform plan
#   terraform apply
#
# Cost estimate: ~$13/mo (B1 App Service) + Cosmos DB free tier (400 RU/s)

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  backend "azurerm" {
    resource_group_name  = "floww-terraform-state"
    storage_account_name = "flowwtfstate"
    container_name       = "tfstate"
    key                  = "prod.terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

# ── Resource Group ────────────────────────────────────────────────────────────

resource "azurerm_resource_group" "floww" {
  name     = "floww-prod-rg"
  location = "eastus"
  tags     = { project = "floww", environment = "production" }
}

# ── App Service Plan (B1) ─────────────────────────────────────────────────────

resource "azurerm_service_plan" "floww" {
  name                = "floww-prod-plan"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  os_type             = "Linux"
  sku_name            = "B1" # ~$13/mo
  tags                = { project = "floww" }
}

# ── Azure Container Registry ──────────────────────────────────────────────────

resource "azurerm_container_registry" "floww" {
  name                = "flowwprodacr"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = { project = "floww" }
}

# ── Cosmos DB (Mongo API) ─────────────────────────────────────────────────────

resource "azurerm_cosmosdb_account" "floww" {
  name                = "floww-prod-cosmos"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  offer_type          = "Standard"
  kind                = "MongoDB"

  capabilities {
    name = "EnableMongo"
  }

  capabilities {
    name = "DisableRateLimitingResponses"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.floww.location
    failover_priority = 0
  }

  tags = { project = "floww" }
}

resource "azurerm_cosmosdb_mongo_database" "floww" {
  name                = "confluence_decoder"
  resource_group_name = azurerm_resource_group.floww.name
  account_name        = azurerm_cosmosdb_account.floww.name
}

# Private endpoint for Cosmos DB (no public access)
resource "azurerm_private_endpoint" "cosmos" {
  name                = "floww-cosmos-pe"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  subnet_id           = azurerm_subnet.floww.id

  private_service_connection {
    name                           = "floww-cosmos-psc"
    private_connection_resource_id = azurerm_cosmosdb_account.floww.id
    subresource_names              = ["MongoDB"]
    is_manual_connection           = false
  }
}

# ── VNet + Subnet ─────────────────────────────────────────────────────────────

resource "azurerm_virtual_network" "floww" {
  name                = "floww-prod-vnet"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  address_space       = ["10.0.0.0/16"]
}

resource "azurerm_subnet" "floww" {
  name                 = "floww-prod-subnet"
  resource_group_name  = azurerm_resource_group.floww.name
  virtual_network_name = azurerm_virtual_network.floww.name
  address_prefixes     = ["10.0.1.0/24"]
}

# ── Key Vault ─────────────────────────────────────────────────────────────────

resource "azurerm_key_vault" "floww" {
  name                = "floww-prod-kv"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  purge_protection_enabled = true
  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = { project = "floww" }
}

data "azurerm_client_config" "current" {}

# Key Vault access policy for the App Service managed identity
resource "azurerm_key_vault_access_policy" "app" {
  key_vault_id = azurerm_key_vault.floww.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.floww.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# ── App Service (FastAPI) ─────────────────────────────────────────────────────

resource "azurerm_linux_web_app" "floww" {
  name                = "floww-prod-app"
  resource_group_name = azurerm_resource_group.floww.name
  location            = azurerm_resource_group.floww.location
  service_plan_id     = azurerm_service_plan.floww.id

  virtual_network_subnet_id = azurerm_subnet.floww.id

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on     = true
    ftps_state    = "Disabled"
    http2_enabled = true

    application_stack {
      docker_image     = "${azurerm_container_registry.floww.login_server}/floww-backend"
      docker_image_tag = "latest"
    }

    ip_restriction_default_action = "Deny"

    # Allow Azure Front Door / health probes
    ip_restriction {
      action     = "Allow"
      ip_address = "0.0.0.0/0" # Restrict in production
      name       = "allow-all-temp"
      priority   = 100
    }
  }

  app_settings = {
    "DOCKER_REGISTRY_SERVER_URL"      = "https://${azurerm_container_registry.floww.login_server}"
    "DOCKER_REGISTRY_SERVER_USERNAME" = azurerm_container_registry.floww.admin_username
    "DOCKER_REGISTRY_SERVER_PASSWORD" = azurerm_container_registry.floww.admin_password
    "ENVIRONMENT"                     = "production"
    "CORS_ORIGINS"                    = "https://floww-prod-app.azurewebsites.net"
    "MONGO_URL"                       = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.mongo_url.id})"
    "DB_NAME"                         = "confluence_decoder"
    "API_SECRET_KEY"                  = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.api_key.id})"
    "WS_API_TOKEN"                    = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.ws_token.id})"
    "DASH_SESSION_TOKEN"              = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.dash_token.id})"
  }

  tags = { project = "floww" }
}

# ── Key Vault Secrets ─────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "mongo_url" {
  name         = "mongo-url"
  value        = azurerm_cosmosdb_account.floww.connection_strings[0]
  key_vault_id = azurerm_key_vault.floww.id
}

resource "azurerm_key_vault_secret" "api_key" {
  name         = "api-secret-key"
  value        = var.api_secret_key
  key_vault_id = azurerm_key_vault.floww.id
}

resource "azurerm_key_vault_secret" "ws_token" {
  name         = "ws-api-token"
  value        = var.ws_api_token
  key_vault_id = azurerm_key_vault.floww.id
}

resource "azurerm_key_vault_secret" "dash_token" {
  name         = "dash-session-token"
  value        = var.dash_session_token
  key_vault_id = azurerm_key_vault.floww.id
}

# ── Budget Alert ──────────────────────────────────────────────────────────────

resource "azurerm_consumption_budget_resource_group" "floww" {
  name              = "floww-monthly-budget"
  resource_group_id = azurerm_resource_group.floww.id

  amount     = 50 # $50/mo budget
  time_grain = "Monthly"

  time_period {
    start_date = "2026-01-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"

    contact_emails = [var.alert_email]
  }
}
