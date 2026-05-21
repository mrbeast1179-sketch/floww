# infra/terraform/outputs.tf

output "app_service_url" {
  description = "URL of the production App Service"
  value       = "https://${azurerm_linux_web_app.floww.default_hostname}"
}

output "acr_login_server" {
  description = "ACR login server for docker push"
  value       = azurerm_container_registry.floww.login_server
}

output "cosmos_connection_string" {
  description = "Cosmos DB connection string"
  value       = azurerm_cosmosdb_account.floww.connection_strings[0]
  sensitive   = true
}

output "key_vault_uri" {
  description = "Key Vault URI for secret references"
  value       = azurerm_key_vault.floww.vault_uri
}

output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.floww.name
}
