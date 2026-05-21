# infra/terraform/variables.tf

variable "api_secret_key" {
  description = "API secret key for X-API-Key header auth"
  type        = string
  sensitive   = true
}

variable "ws_api_token" {
  description = "WebSocket connection token"
  type        = string
  sensitive   = true
}

variable "dash_session_token" {
  description = "Dashboard session token"
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "Email for budget alerts"
  type        = string
  default     = "nav@example.com"
}
