# AWS SECURITY

Status: IMPLEMENTATION IN PROGRESS

## Runtime

AWS EC2 hosts always-on workers:
data ingestion
canonicalization
quant
news
analysis
scenario
Telegram
alerting
health monitor

Supabase remains the database of record.

Vercel hosts the customer web application.

## Required controls

IAM:
- dedicated instance role
- least privilege
- no long-lived access keys on disk

SSH:
- key-based access only
- no password SSH
- restricted source CIDR
- SSM preferred where practical

Network:
- HTTPS/TLS for public endpoints
- security group exposes only required ports
- database access restricted to approved server paths

Secrets:
- AWS Secrets Manager or SSM Parameter Store
- no secrets in Git
- no tokens in browser bundles
- rotation schedule documented

Process:
- Docker or systemd
- health checks
- restart policy
- structured JSON logs
- graceful shutdown
- deployment version metadata

Observability:
- /health
- /ready
- /metrics
- CloudWatch logs/metrics
- alert on stale ingestion, worker death and repeated API errors

Recovery:
- EC2 replacement procedure
- deployment rollback
- Supabase backup/recovery procedure
- raw data replay path
- idempotent dataset-version writes

## Security gates

Before production:
- dependency pin/lock
- secret scan
- IAM review
- network review
- backup restore test
- incident runbook
- customer tenant isolation test
- API key rotation/revocation test
