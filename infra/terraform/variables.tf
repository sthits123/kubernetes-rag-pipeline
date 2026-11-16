variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short prefix used for resource names."
  type        = string
  default     = "kubernetes-rag"
}

variable "allowed_ingress_cidr" {
  description = "Trusted client IPv4 CIDR permitted to reach the web UI, e.g. 203.0.113.10/32."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.allowed_ingress_cidr)) && var.allowed_ingress_cidr != "0.0.0.0/0"
    error_message = "Set allowed_ingress_cidr to a valid IPv4 CIDR. Do not use 0.0.0.0/0 for the unauthenticated UI."
  }
}

variable "certificate_arn" {
  description = "Optional ACM certificate ARN for HTTPS. When set, HTTP redirects to HTTPS."
  type        = string
  default     = ""
}

variable "bedrock_chat_model_id" {
  description = "Bedrock model ID used for planning and answer generation."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "bedrock_guardrail_model_id" {
  description = "Bedrock model ID used by NeMo Guardrails."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock embedding model ID."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_embedding_dimensions" {
  description = "Titan Text Embeddings V2 output size (256, 512, or 1024)."
  type        = number
  default     = 1024

  validation {
    condition     = contains([256, 512, 1024], var.bedrock_embedding_dimensions)
    error_message = "Titan Text Embeddings V2 dimensions must be 256, 512, or 1024."
  }
}

variable "image_tag" {
  description = "Container tag to deploy from the project ECR repository."
  type        = string
  default     = "latest"
}

variable "desired_count" {
  description = "ECS task count. Start at zero until the image is pushed, then set to one."
  type        = number
  default     = 0
}

variable "vpc_cidr" {
  description = "CIDR block for the application VPC."
  type        = string
  default     = "10.40.0.0/16"
}
