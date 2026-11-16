# Kubernetes RAG Pipeline

A retrieval-augmented generation application for asking questions about your
technical documents. It provides a FastAPI backend, a Streamlit chat interface,
and two provider configurations:

| Environment | Chat and embeddings | Vector search | Document storage |
|---|---|---|---|
| Local development | Ollama | Qdrant | Local files |
| AWS deployment | Amazon Bedrock | OpenSearch Serverless | Amazon S3 |

The AWS deployment runs on Amazon ECS with AWS Fargate. ECS task roles provide
AWS credentials; do not put AWS access keys in the application configuration.

## Features

- Ingests PDF, DOCX, PPTX, HTML, Markdown, and plain-text files.
- Retrieves relevant document chunks for technical questions.
- Uses Amazon Bedrock for chat and embeddings in AWS mode.
- Stores source files in S3 and vectors in OpenSearch Serverless in AWS mode.
- Supports local development with Ollama and Qdrant.

## Local development

### Prerequisites

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker
- [Ollama](https://ollama.com/)

### Install and configure

From the repository root:

```bash
uv sync
cp .env.example .env
```

Keep `RAG_PROVIDER=local` in `.env`. Start Qdrant:

```bash
docker run --name rag-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  -d qdrant/qdrant
```

Start Ollama in a separate terminal and download the chat and embedding models:

```bash
ollama serve
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Ingest documents

Place supported documents in `./data`, then run:

```bash
uv run python -m app.ingestion.processor ./data
```

The command parses files, splits text into chunks, generates embeddings with
Ollama, and writes the vectors and source paths to Qdrant.

### Run the application

Start the API and Streamlit UI in separate terminals:

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
uv run streamlit run ui/app.py
```

Open the chat UI at `http://localhost:8501`. The API documentation is available
at `http://localhost:8000/docs`.

## AWS architecture

The Terraform configuration in `infra/terraform/` provisions:

- ECS Fargate for the FastAPI service and Streamlit UI.
- Amazon Bedrock for chat and embedding inference.
- OpenSearch Serverless for vector indexing and retrieval, with private VPC
  access.
- A private, encrypted, versioned S3 bucket for source documents.
- Amazon ECR, CloudWatch Logs, an Application Load Balancer, and a VPC with
  private application subnets.

The example deployment restricts load balancer access to a configured client
CIDR. The demo UI does not currently have user sign-in. For production, configure
HTTPS with an ACM certificate and add an authentication layer before making it
available to a broader audience.

## Deploy to AWS

### Prerequisites

- AWS CLI v2, Docker, Terraform 1.6+, and `jq`
- An AWS account with permissions to create the resources in the Terraform
  configuration
- Amazon Bedrock model access enabled in `us-east-1`
- A trusted public IPv4 address/CIDR for restricting UI access

The NAT gateway, load balancer, Fargate tasks, and OpenSearch Serverless may
incur ongoing charges. Review the Terraform plan and expected costs before
provisioning.

### 1. Configure and review infrastructure

From the repository root:

```bash
aws configure
aws sts get-caller-identity
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and replace the example
`allowed_ingress_cidr` (`203.0.113.10/32`) with your trusted public IP/CIDR.
Keep `desired_count = 0` for the initial infrastructure setup. To enable HTTPS,
set `certificate_arn` to an ACM certificate ARN in `us-east-1`.

Initialize Terraform and review the plan:

```bash
terraform init
terraform validate
terraform plan
```

When you are ready to create the resources, run:

```bash
terraform apply
```

### 2. Build and push the application image

Return to the repository root:

```bash
cd ../..
export AWS_REGION=us-east-1
ECR_URI=$(terraform -chdir=infra/terraform output -raw ecr_repository_url)

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ECR_URI%%/*}"

docker build --platform linux/amd64 -t "$ECR_URI:initial" .
docker push "$ECR_URI:initial"
```

The `image_tag` in `terraform.tfvars` defaults to `initial`. Use a new immutable
tag for each subsequent release and update that variable before applying.

### 3. Upload and index documents

Put supported documents under `./data`, then upload them to the S3 bucket:

```bash
BUCKET=$(terraform -chdir=infra/terraform output -raw s3_document_bucket)
aws s3 sync ./data "s3://$BUCKET/documents/"
```

Run the one-off Fargate ingestion task. It reads documents from S3, generates
embeddings with Bedrock, and indexes them in the private OpenSearch collection:

```bash
CLUSTER=$(terraform -chdir=infra/terraform output -raw ecs_cluster_name)
TASK_DEF=$(terraform -chdir=infra/terraform output -raw ingestion_task_definition_arn)
SUBNETS=$(terraform -chdir=infra/terraform output -json private_subnet_ids | jq -r 'join(",")')
TASK_SG=$(terraform -chdir=infra/terraform output -raw task_security_group_id)

TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$TASK_SG],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' \
  --output text)

aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK_ARN"
aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].{lastStatus:lastStatus,exitCode:containers[0].exitCode,stoppedReason:stoppedReason}'
```

Confirm the ingestion task exited with code `0` before starting the application.

### 4. Start the application

In `infra/terraform/terraform.tfvars`, change `desired_count` to `1`, then run:

```bash
cd infra/terraform
terraform apply
terraform output -raw ui_url
```

Open the URL printed by Terraform. Application logs are available in the
CloudWatch log group created for this deployment.

## Configuration

See [.env.example](./.env.example) for the application settings. Set
`RAG_PROVIDER=local` for local development; AWS task definitions set
`RAG_PROVIDER=aws` and configure Bedrock, OpenSearch, and S3. In AWS, the AWS SDK
uses the ECS task role for service authentication.

To index local files in AWS mode, run the ingestion command with AWS credentials
and network access to the private OpenSearch endpoint:

```bash
RAG_PROVIDER=aws uv run python -m app.ingestion.processor ./data
```

For the deployed setup, upload documents to S3 and use the one-off ECS task
described above. Do not commit `.env`, `terraform.tfvars`, credentials, or
document data.

## Validation

Run the AWS adapter tests:

```bash
uv run --locked python -m unittest discover -s tests -v
```

Validate the Terraform configuration without deploying:

```bash
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```
