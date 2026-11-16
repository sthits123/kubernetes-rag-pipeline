output "ecr_repository_url" {
  description = "Push the application image to this ECR repository."
  value       = aws_ecr_repository.app.repository_url
}

output "ui_url" {
  description = "Application Load Balancer URL for the Streamlit UI."
  value       = "${var.certificate_arn == "" ? "http" : "https"}://${aws_lb.app.dns_name}"
}

output "s3_document_bucket" {
  description = "S3 bucket for ingested source files."
  value       = aws_s3_bucket.documents.bucket
}

output "opensearch_endpoint" {
  description = "Private OpenSearch Serverless collection endpoint."
  value       = aws_opensearchserverless_collection.vectors.collection_endpoint
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "ingestion_task_definition_arn" {
  value = aws_ecs_task_definition.ingestion.arn
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "task_security_group_id" {
  value = aws_security_group.tasks.id
}
