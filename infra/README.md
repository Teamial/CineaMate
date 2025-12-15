# Infra (Terraform + LocalStack)

This directory encodes AWS-style infrastructure for Cinemate, designed to run **locally** using **LocalStack** (no cloud spend).

## Prereqs
- Docker (to run LocalStack)
- Terraform installed locally

## Quickstart
1) Start LocalStack (and the rest of the dev stack):

```bash
make dev
```

2) Terraform plan/apply for an environment:

```bash
make infra-plan ENV=staging
make infra-apply ENV=staging
```

## Environments
- `infra/environments/staging`
- `infra/environments/production`

These are separated so you can model real promotion workflows (staging first, then prod).

## Rollbacks
In GitHub Actions, production deploys are triggered via `workflow_dispatch` with an `image_tag`.
To rollback, redeploy a previously known-good tag (for example `sha-abcdef1`).


