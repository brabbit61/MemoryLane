resource "aws_s3_bucket" "photos" {
  bucket = "${var.project_name}-${var.environment}-photos"

  tags = {
    Name = "${var.project_name}-${var.environment}-photos"
  }
}

resource "aws_s3_bucket_versioning" "photos" {
  bucket = aws_s3_bucket.photos.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket = aws_s3_bucket.photos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    id     = "transition-old-photos"
    status = "Enabled"

    # Empty filter applies the rule to all objects in the bucket.
    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

# Terraform state bucket (separate)
resource "aws_s3_bucket" "model_artifacts" {
  bucket = "${var.project_name}-${var.environment}-model-artifacts"

  tags = {
    Name = "${var.project_name}-${var.environment}-model-artifacts"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
