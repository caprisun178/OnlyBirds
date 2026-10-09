# Production on AWS or another cloud (alternative)

> **Status:** Proposal, for discussion. This is the **alternative** to
> [Production environment (self-hosted)](production-environment.md): the
> same app and the same requirements (R1–R30 on that page all still
> apply), hosted on **AWS** or a comparable cloud instead of our own VPS.
> This page covers what we'd have to do, what it costs, and how it compares.
> Prices are approximate (US East, October 2026); confirm with the
> [AWS Pricing Calculator](https://calculator.aws/) before committing.
> Risks from the external data APIs apply to every option and are covered in
> [External services & API risk](external-services.md).

## 1. The short version

There are two very different ways to "be on AWS":

| | **A. A server on AWS** (Lightsail / EC2) | **B. AWS-managed services** (ECS + RDS + S3 …) |
|---|---|---|
| What it is | The self-hosted plan, unchanged, on an AWS virtual machine | Each piece runs on a managed AWS service |
| We still manage the OS, Postgres, backups? | **Yes**, same as self-hosted | **No.** AWS patches, backs up and fails over |
| Work to set up | low (same Docker Compose setup) | medium–high (networking, IAM, infrastructure-as-code) |
| Monthly cost (launch scale) | **≈ $45–55** | **≈ $90–130** |
| Upkeep | ~2–4 h/month (same as self-hosted) | ~1 h/month, but more AWS knowledge needed |
| Scales beyond one server | manual (resize) | built in (more containers, bigger database, multi-AZ) |
| Lock-in | low | medium (S3/Cognito/IAM-specific code and config) |

**Recommendation:** at launch scale, **option B is the "pay more to manage
less" choice**, and only worth it if the team wants AWS experience, has AWS
credits, or needs high availability. Otherwise the self-hosted VPS (or
option A, if it must be AWS) does the same job for a third of the price.

## 2. Option A: a server on AWS (Lightsail or EC2)

Everything in [the self-hosted plan](production-environment.md) applies
as written: Docker Compose with Caddy + FastAPI + PostGIS + backups. Only
the machine changes.

- **Lightsail** is AWS's simple fixed-price VPS product: an 8 GB / 2 vCPU
  instance is about **$44/month** including a public IPv4 address and a
  generous transfer allowance. That's simplest and most predictable.
- **EC2** (e.g. `t4g.large`, 2 vCPU / 8 GB, ARM) is similar per month
  on-demand, cheaper with a 1–3 year commitment. You'd add an EBS volume,
  a security group (the firewall) and an Elastic IP.
- **Backups:** the off-site backup target can be **S3** (restic supports it
  natively, roughly $0.023/GB-month), plus Lightsail/EBS snapshots for fast
  machine rollback.
- **Watch:** ARM instances (`t4g`, Graviton) are cheaper, but check that
  `torch` / BioCLIP wheels install and perform well on ARM first.

Compared with a Hetzner VPS (≈ €7 for 8 GB) this costs roughly 5–6× more
for the same machine. What AWS adds is being inside the AWS ecosystem (S3,
SES, IAM) and an easy path to option B later.

## 3. Option B: AWS-managed services

### 3.1 Architecture

```text
                        users (browser / PWA)
                                │ HTTPS
                     Route 53 (DNS) + ACM (TLS certificates)
                 ┌──────────────┴───────────────┐
                 ▼                              ▼
   CloudFront ─► S3 (frontend/ static site)   Application Load Balancer
   CloudFront ─► S3 (photos, private bucket;          │
                 served via CloudFront)               ▼
                                    ECS Fargate service "api"
                                    FastAPI + BioCLIP container (image in ECR)
                                    1–2 tasks, 1 vCPU / 4 GB each
                                                │ private subnet / security group
                                                ▼
                                    RDS PostgreSQL 16 + PostGIS
                                    automated backups + point-in-time recovery
   Cognito (sign-in) or our own auth in the API
   SES (email) · Secrets Manager (keys) · CloudWatch (logs, metrics, alarms)
```

| Need | AWS service | Notes |
|---|---|---|
| Run the API | **ECS on Fargate** (or the newer *ECS Express Mode*) | Containers without managing servers. **Not App Runner:** AWS moved it to maintenance and it [stopped accepting new customers on April 30, 2026](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html); Express Mode is AWS's suggested replacement. |
| Load balancer + HTTPS | **ALB** + **ACM** certificate | ACM certificates are free and auto-renew. |
| Database | **RDS for PostgreSQL** (PostGIS is supported as an extension) | Automated daily backups with **point-in-time recovery** up to 35 days are included. Multi-AZ (a hot standby in another datacenter) roughly doubles the price; add it later. |
| Photos | **S3** (private) + **CloudFront** | Uploads via presigned URLs; EXIF still stripped by the API. |
| Frontend | **S3 + CloudFront** | Static hosting; same `frontend/` folder. |
| Sign-in | **Cognito**, or our own (as in the self-hosted plan) | Cognito's free tier covers far more users than we'll have at launch; ties us to AWS. |
| Email | **SES** | Cheapest relay ($0.10 per 1,000); new accounts start in the SES "sandbox" and must request production access. |
| Secrets | **Secrets Manager** / SSM Parameter Store | ~$0.40 per secret per month (Parameter Store standard is free). |
| Logs, metrics, alarms | **CloudWatch** | Alarms to email/SMS via SNS. Errors could still go to Sentry/GlitchTip. |
| DNS | **Route 53** | $0.50 per hosted zone per month. |
| Container images | **ECR** | Pennies at our size. |

### 3.2 What we'd have to do

Beyond the app changes the self-hosted plan already lists (sign-in, EXIF
stripping, Dockerfile, production settings, rate limits, geocoder swap):

1. **AWS account setup, done properly:**
    - Use an AWS **Organization**, and lock the root user (MFA, never used day-to-day).
    - Sign in through **IAM Identity Center** with personal accounts, one per person.
    - Set up **AWS Budgets** alerts on day one. AWS bills are usage-based and easy
      to overspend by accident (a forgotten NAT gateway alone is ~$32/month).
2. **Infrastructure as code:** describe everything in **Terraform** or
   **AWS CDK**, kept in the repo (`deploy/aws/`). Click-ops in the AWS
   console is hard to reproduce and review.
3. **Networking (VPC):** public subnets for the load balancer, private
   subnets for RDS. **Avoid NAT gateway costs:** either run Fargate tasks in
   public subnets behind tight security groups, or add VPC endpoints. The
   API needs outbound internet for eBird/iNaturalist either way.
4. **Code changes specific to AWS:**
    - `dao/storage.py` → S3 via `boto3`, with presigned upload URLs.
    - Sign-in → Cognito JWT verification (if Cognito is chosen).
    - `dao/email.py` → SES SMTP credentials (configuration only).
    - BioCLIP weights baked into the container image, so a new task
      doesn't download 571 MB from Hugging Face on every start.
5. **CI/CD:**
    - GitHub Actions authenticates to AWS with **OIDC**, so no long-lived AWS keys
      are stored in GitHub.
    - The pipeline builds the image, pushes it to ECR, runs migrations as a
      one-off ECS task, then updates the service. ECS does rolling,
      health-checked deploys.
6. **Migrate data** (optional) from Neon with `pg_dump` → RDS.
7. **Request SES production access** and verify the domain (SPF/DKIM/DMARC).
8. **Runbook:** restore RDS to a point in time, roll back an ECS deploy,
   rotate secrets.

Realistic setup effort: **1–3 weeks** for someone new to AWS, mostly
IAM, networking and infrastructure-as-code. Allow a few days if someone on the
team already knows AWS.

### 3.3 Cost estimate (launch scale, us-east-1)

| Item | Size | ≈ $ / month |
|---|---|---|
| ECS Fargate API | 1 task, 1 vCPU / 4 GB, always on (ARM is ~20% cheaper) | 35–45 |
| Application Load Balancer | base + light traffic | 18–25 |
| RDS PostgreSQL | `db.t4g.small` (2 vCPU / 2 GB), single-AZ, 30 GB gp3 | 25–30 |
| Public IPv4 addresses | AWS charges ~$3.65/month per public IPv4 address (ALB uses 2+) | 7–15 |
| S3 + CloudFront | photos + frontend, low traffic | 1–5 |
| CloudWatch logs/alarms | | 3–8 |
| Secrets, Route 53, ECR | | 2–4 |
| SES / Cognito | free tier / pennies | 0–2 |
| **Total** | | **≈ $90–130** |
| Later: second API task (high availability) | | +35–45 |
| Later: RDS Multi-AZ | | +25–30 |

[RDS pricing reference](https://aws.amazon.com/rds/postgresql/pricing):
`db.t4g.small` single-AZ is about $23/month before storage. New AWS
accounts get some free-tier credits for the first months; check the
current offer, as it changed in 2025.

## 4. Other clouds and platforms

The same two shapes exist everywhere. A "server" option is the self-hosted
plan on their VM; a "managed" option maps roughly like this:

| Provider | Run the API | Database (PostGIS) | Files | Notes |
|---|---|---|---|---|
| **AWS** | ECS Fargate / Express Mode | RDS PostgreSQL | S3 | Most services and documentation; most configuration. |
| **Google Cloud** | Cloud Run | Cloud SQL for PostgreSQL | Cloud Storage | Cloud Run is the simplest container host of the big three. **Set minimum instances = 1**, or every cold start reloads BioCLIP (~571 MB). |
| **Azure** | Container Apps | Azure Database for PostgreSQL (Flexible Server) | Blob Storage | Comparable to AWS; good if anyone has Microsoft credits. |
| **DigitalOcean** | App Platform, or a Droplet (VM) | Managed PostgreSQL | Spaces (S3-compatible) | Simpler and cheaper than the big three; fewer services. |
| **Render + Supabase** (managed PaaS) | Render Standard | Supabase Pro | Supabase Storage | The "rent each piece" option: ≈ $50–70/month, least setup. Kept here for comparison. |

## 5. Side-by-side

| | Self-hosted VPS | AWS option A (Lightsail/EC2) | AWS option B (managed) | Render + Supabase |
|---|---|---|---|---|
| ≈ Monthly cost | €15–20 | $45–55 | $90–130 | $50–70 |
| We control the OS / own the stack | **fully** | **fully** | partly | no |
| Who does backups | us | us (S3 as target) | AWS (PITR included) | provider |
| Who patches OS / Postgres | us | us | AWS | provider |
| Setup effort | days | days | 1–3 weeks | ~1 day |
| Ongoing upkeep | 2–4 h/month | 2–4 h/month | ~1 h/month | ~0.5 h/month |
| High availability later | add a 2nd server (manual) | same | toggle Multi-AZ / add tasks | upgrade plans |
| Vendor lock-in | lowest | low | medium | medium |
| Fits "own things myself" | **best** | good | weaker | weakest |

**Bottom line:** if owning the stack matters most, the
[self-hosted VPS](production-environment.md) is the best fit, and AWS
option A is the same plan at a higher price. AWS option B makes sense if
the goals shift to minimal operations work, high availability, or using
cloud credits.

## 6. Open decisions

1. Which matters more for production: **ownership/cost** (self-hosted /
   option A) or **least operations work** (option B / PaaS)?
2. Any **cloud credits** available (AWS Activate, education programs,
   Google for Startups)? Credits can make option B effectively free for a
   year.
3. If AWS: **Terraform or CDK** for infrastructure-as-code?
4. If AWS: **Cognito or our own sign-in?** Our own keeps the app portable
   between all options above.

## Related pages

- [Production environment (self-hosted)](production-environment.md): the primary proposal, and the requirement list (R1–R30) this page reuses
- [External services & API risk](external-services.md): applies to every hosting option
- [Deployment](deployment.md): the current dev setup
