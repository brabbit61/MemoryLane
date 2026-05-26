output "photos_bucket_name" {
  description = "S3 bucket for photo storage"
  value       = module.s3.photos_bucket_name
}
