resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-${var.environment}"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = false
  }

  schema {
    name                = "tenant_id"
    attribute_data_type = "String"
    mutable             = false

    string_attribute_constraints {
      min_length = 36
      max_length = 36
    }
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-user-pool"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_name}-${var.environment}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  supported_identity_providers = ["COGNITO"]

  callback_urls = var.environment == "prod" ? [
    "https://memorylane.example.com/callback"
  ] : ["http://localhost:3000/callback"]

  logout_urls = var.environment == "prod" ? [
    "https://memorylane.example.com"
  ] : ["http://localhost:3000"]
}
