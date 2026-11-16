data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  name = "${var.project_name}-${random_id.suffix.hex}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "app" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name}-vpc" }
}

resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id
  tags   = { Name = "${local.name}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.app.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.app.id
  availability_zone = local.azs[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  tags              = { Name = "${local.name}-private-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.app.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app.id
  }
  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name}-nat" }
}

resource "aws_nat_gateway" "app" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.app]
  tags          = { Name = "${local.name}-nat" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.app.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.app.id
  }
  tags = { Name = "${local.name}-private" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Allow the approved client CIDR to access the Streamlit UI."
  vpc_id      = aws_vpc.app.id

  ingress {
    description = "Streamlit web UI"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ingress_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  count             = var.certificate_arn == "" ? 0 : 1
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from the approved client CIDR"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = var.allowed_ingress_cidr
}

resource "aws_security_group" "tasks" {
  name        = "${local.name}-tasks"
  description = "Only the ALB can reach the Streamlit container."
  vpc_id      = aws_vpc.app.id

  ingress {
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "opensearch_vpce" {
  name        = "${local.name}-aoss-vpce"
  description = "Allow HTTPS from the ECS tasks to the OpenSearch Serverless VPC endpoint."
  vpc_id      = aws_vpc.app.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_s3_bucket" "documents" {
  bucket        = "${local.name}-documents"
  force_destroy = false
  tags          = { Name = "${local.name}-documents" }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${local.name}-encryption"
  type = "encryption"
  policy = jsonencode({
    Rules       = [{ ResourceType = "collection", Resource = ["collection/${local.name}"] }]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_collection" "vectors" {
  name       = local.name
  type       = "VECTORSEARCH"
  depends_on = [aws_opensearchserverless_security_policy.encryption]
  tags       = { Name = local.name }
}

resource "aws_opensearchserverless_vpc_endpoint" "vectors" {
  name               = "${local.name}-endpoint"
  vpc_id             = aws_vpc.app.id
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.opensearch_vpce.id]
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${local.name}-network"
  type = "network"
  policy = jsonencode([
    {
      Description = "Private access from the application VPC endpoint"
      Rules = [
        { ResourceType = "collection", Resource = ["collection/${local.name}"] },
        { ResourceType = "dashboard", Resource = ["collection/${local.name}"] }
      ]
      AllowFromPublic = false
      SourceVPCEs     = [aws_opensearchserverless_vpc_endpoint.vectors.id]
    }
  ])
}

resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "app" {
  name = local.name
}

resource "aws_iam_role" "task_execution" {
  name = "${local.name}-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name = "${local.name}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "task" {
  name = "${local.name}-runtime"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_chat_model_id}",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_guardrail_model_id}",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = [aws_opensearchserverless_collection.vectors.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.documents.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.documents.arn}/*"]
      }
    ]
  })
}

resource "aws_opensearchserverless_access_policy" "vectors" {
  name = "${local.name}-data"
  type = "data"
  policy = jsonencode([
    {
      Description = "Allow the ECS task role to manage its vector index"
      Principal   = [aws_iam_role.task.arn]
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.name}"]
          Permission   = ["aoss:DescribeCollectionItems"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${local.name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex"
          ]
        }
      ]
    }
  ])
}

resource "aws_lb" "app" {
  name               = substr(local.name, 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "ui" {
  name        = substr("${local.name}-ui", 0, 32)
  port        = 8501
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.app.id

  health_check {
    path                = "/_stcore/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = var.certificate_arn == "" ? "forward" : "redirect"
    target_group_arn = var.certificate_arn == "" ? aws_lb_target_group.ui.arn : null

    dynamic "redirect" {
      for_each = var.certificate_arn == "" ? [] : [1]
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ui.arn
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential    = true
      command      = ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "RAG_PROVIDER", value = "aws" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "BEDROCK_CHAT_MODEL_ID", value = var.bedrock_chat_model_id },
        { name = "BEDROCK_GUARDRAIL_MODEL_ID", value = var.bedrock_guardrail_model_id },
        { name = "BEDROCK_EMBEDDING_MODEL_ID", value = var.bedrock_embedding_model_id },
        { name = "BEDROCK_EMBEDDING_DIMENSIONS", value = tostring(var.bedrock_embedding_dimensions) },
        { name = "OPENSEARCH_ENDPOINT", value = aws_opensearchserverless_collection.vectors.collection_endpoint },
        { name = "OPENSEARCH_INDEX", value = "kubernetes-rag" },
        { name = "S3_BUCKET", value = aws_s3_bucket.documents.bucket },
        { name = "S3_DOCUMENT_PREFIX", value = "documents" },
        { name = "USE_SEMANTIC_CACHE", value = "false" },
        { name = "LOGFIRE_TOKEN", value = "" }
      ]
      healthCheck = {
        command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    },
    {
      name         = "ui"
      image        = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential    = true
      command      = ["uv", "run", "--no-sync", "streamlit", "run", "ui/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
      portMappings = [{ containerPort = 8501, protocol = "tcp" }]
      environment = [
        { name = "BACKEND_URL", value = "http://127.0.0.1:8000" },
        { name = "LOGFIRE_TOKEN", value = "" }
      ]
      dependsOn = [{ containerName = "api", condition = "HEALTHY" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ui"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "ingestion" {
  family                   = "${local.name}-ingestion"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "ingestion"
      image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential = true
      command   = ["uv", "run", "--no-sync", "python", "-m", "app.ingestion.processor", "--s3-prefix", "documents"]
      environment = [
        { name = "RAG_PROVIDER", value = "aws" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "BEDROCK_EMBEDDING_MODEL_ID", value = var.bedrock_embedding_model_id },
        { name = "BEDROCK_EMBEDDING_DIMENSIONS", value = tostring(var.bedrock_embedding_dimensions) },
        { name = "OPENSEARCH_ENDPOINT", value = aws_opensearchserverless_collection.vectors.collection_endpoint },
        { name = "OPENSEARCH_INDEX", value = "kubernetes-rag" },
        { name = "S3_BUCKET", value = aws_s3_bucket.documents.bucket },
        { name = "S3_DOCUMENT_PREFIX", value = "documents" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ingestion"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "app" {
  name            = "${local.name}-service"
  cluster         = aws_ecs_cluster.app.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "ui"
    container_port   = 8501
  }

  depends_on = [
    aws_lb_listener.http,
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.task_execution,
    aws_iam_role_policy.task,
    aws_opensearchserverless_access_policy.vectors,
    aws_opensearchserverless_security_policy.network
  ]
}
