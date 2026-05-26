terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket       = "memorylane-terraform-state"
    key          = "state/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "MemoryLane"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

module "s3" {
  source = "./modules/s3"

  project_name = var.project_name
  environment  = var.environment
}
