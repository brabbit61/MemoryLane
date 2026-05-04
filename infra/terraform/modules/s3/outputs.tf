output "photos_bucket_name" {
  value = aws_s3_bucket.photos.bucket
}

output "photos_bucket_arn" {
  value = aws_s3_bucket.photos.arn
}

output "model_artifacts_bucket_name" {
  value = aws_s3_bucket.model_artifacts.bucket
}
