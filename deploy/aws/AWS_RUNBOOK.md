# AWS RUNBOOK

Status: NOT DEPLOYED

## Target

Region: ap-southeast-1

EC2 hosts the always-on workers and API.
Supabase remains the persistent database.
Vercel remains the web frontend.

## Required services

oi-api
oi-ingestion
oi-news
oi-analysis
oi-scenario
oi-telegram
oi-alert
oi-health

## Health

/health = process alive
/ready = canonical data available and VALID when canonical reads are enabled
/metrics = service-level metrics scaffold

## Deployment

1. Provision least-privilege IAM instance role.
2. Install patched Python/runtime and Docker or systemd.
3. Install env file from AWS Secrets Manager/SSM.
4. Deploy immutable git/container version.
5. Start systemd units.
6. Verify /health.
7. Verify /ready.
8. Check structured logs.
9. Check database connectivity.
10. Run rollback drill.

## Rollback

Pin previous release SHA/image.
Stop current service.
Start previous service.
Verify /health and /ready.
Record deployment incident metadata.

## Production gate

No AWS production deployment should be treated as complete until canonical
ingestion, PIT, customer auth, monitoring, backup and E2E gates have passed.
