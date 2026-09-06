# InterviewIQ Deployment Readiness

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Production Architecture                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Frontend   │      │    Backend   │      │   Database   │  │
│  │  (Vercel/    │◄────►│  (Render Web │◄────►│  (PostgreSQL)│  │
│  │  Static)     │      │  Service)    │      │              │  │
│  └──────────────┘      └──────┬───────┘      └──────────────┘  │
│                               │                                 │
│                    ┌──────────┴──────────┐                      │
│                    ▼                     ▼                      │
│            ┌─────────────┐       ┌─────────────┐               │
│            │   Worker    │       │   S3/Object │               │
│            │  Service    │       │   Storage   │               │
│            └─────────────┘       └─────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Service Definitions

### 1. Web Service (Render Web Service)
- **Runtime**: Python 3.11+
- **Command**: `DEPLOY_MODE=remote INTERVIEWIQ_DISABLE_WORKERS=1 uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- **Health Check**: `GET /health`
- **Environment**: All production variables (see `.env.example`)

### 2. Background Worker Service (Render Worker)
- **Runtime**: Python 3.11+
- **Command**: `python -m app.workers`
- **Environment**: Same as web service but `INTERVIEWIQ_DISABLE_WORKERS=0`

### 3. PostgreSQL Database (Render Managed)
- **Version**: PostgreSQL 15+
- **Connection**: Via `DATABASE_URL` environment variable

### 4. S3-Compatible Object Storage
- **Providers**: AWS S3, MinIO, Cloudflare R2, Backblaze B2, etc.
- **Configuration**: `STORAGE_BACKEND=s3` + credentials

---

## Required Environment Variables

See `.env.example` for complete list. Critical variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string |
| `DEPLOY_MODE` | Yes | `remote` for production |
| `INTERVIEWIQ_DISABLE_WORKERS` | Yes | `1` for web, `0` for worker |
| `STORAGE_BACKEND` | Yes | `s3` for production |
| `S3_BUCKET` | Yes (S3) | Bucket name |
| `S3_ACCESS_KEY_ID` | Yes (S3) | Access key |
| `S3_SECRET_ACCESS_KEY` | Yes (S3) | Secret key |
| `FRONTEND_ORIGIN` | Yes | CORS origin (e.g., `https://app.example.com`) |
| `PUBLIC_APP_URL` | Yes | Frontend public URL |
| `GROQ_API_KEY` | No | LLM provider key |
| `AUTH_SECRET` | Yes | HMAC secret (generate: `openssl rand -hex 32`) |
| `GMAIL_REDIRECT_URI` | Yes (Gmail) | OAuth redirect for Gmail |
| `CALENDAR_REDIRECT_URI` | Yes (Calendar) | OAuth redirect for Calendar |
| `LINKEDIN_REDIRECT_URI` | Yes (LinkedIn) | OAuth redirect for LinkedIn |
| `LINKEDIN_CLIENT_ID` | Yes (LinkedIn) | LinkedIn app client ID |
| `LINKEDIN_CLIENT_SECRET` | Yes (LinkedIn) | LinkedIn app secret |

---

## OAuth Provider Configuration

### Google Cloud Console (Gmail + Calendar)
1. Create project at https://console.cloud.google.com
2. Enable APIs: Gmail API, Google Calendar API
3. Create OAuth 2.0 Client ID (Web application)
4. Add authorized redirect URIs:
   - Gmail: `https://api.yourdomain.com/api/settings/gmail/callback`
   - Calendar: `https://api.yourdomain.com/api/settings/calendar/callback`
5. Set `GMAIL_REDIRECT_URI` and `CALENDAR_REDIRECT_URI`

### LinkedIn Developer Portal
1. Create app at https://www.linkedin.com/developers/apps
2. Products: "Sign In with LinkedIn using OpenID Connect" + "Share on LinkedIn"
3. Scopes: `openid`, `profile`, `email`, `w_member_social`
4. Add redirect URI: `https://api.yourdomain.com/api/integrations/linkedin/callback`
5. Set `LINKEDIN_REDIRECT_URI`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`

---

## Database Migration Procedure

### Local SQLite to Production PostgreSQL

```bash
# 1. Set environment variables
export DATABASE_URL="postgresql://user:pass@host:port/db"
export SQLITE_PATH="./data/app.db"

# 2. Run migration script
python scripts/migrate_sqlite_to_pg.py
```

The script will:
1. Read all tables from SQLite
2. Create matching tables in PostgreSQL
3. Copy all data preserving IDs, timestamps, FKs
4. Verify row counts match

### Verification
```bash
# The script outputs row count comparison
# Example output:
#   ✓ users: SQLite=5, PostgreSQL=5
#   ✓ candidates: SQLite=12, PostgreSQL=12
#   ✓ Migration completed successfully!
```

---

## S3 Storage Setup

### AWS S3
1. Create bucket in desired region
2. Create IAM user with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` permissions
3. Configure CORS for bucket (if needed for direct uploads)

### MinIO (Self-hosted)
```bash
# Set endpoint URL
S3_ENDPOINT_URL=https://minio.yourdomain.com
S3_REGION=us-east-1
```

### Cloudflare R2
```bash
# Use R2 endpoint
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
```

---

## Worker Deployment

The worker process handles:
1. **Screening Queue** - Processes `screening_jobs` table (5s poll)
2. **Notification Outbox** - Sends emails via Gmail (5s poll)
3. **Gmail Polling** - Checks for new applications (10min poll, remote only)

### Render Worker Service
- Separate service type: `worker`
- Same codebase, different entry point: `python -m app.workers`
- `INTERVIEWIQ_DISABLE_WORKERS=0`

### Local Development
```bash
# Run workers in same process (default)
python -m api.main

# Run workers separately
INTERVIEWIQ_DISABLE_WORKERS=1 python -m api.main &
python -m app.workers
```

---

## Frontend Deployment (Vercel)

### Build Configuration
- **Framework**: Next.js 14 (Static Export)
- **Output**: `frontend/out/`
- **Build Command**: `npm run build`

### Environment Variables (Vercel)
```
NEXT_PUBLIC_APP_URL=https://app.yourdomain.com
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

### Rewrites (vercel.json)
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "https://api.yourdomain.com/api/$1" }
  ]
}
```

---

## Electron Production Build

### Configuration
- `backend_mode: "remote"` in settings
- `remote_api_url: "https://api.yourdomain.com"`

### Build Process
```bash
cd electron
npm run build
# Outputs distributable in dist/
```

### Auto-update
- Configure `electron-updater` with GitHub Releases or S3
- Set `INTERVIEWIQ_DEFAULT_REMOTE_URL` at build time

---

## Health Checks

### Web Service: `GET /health`
```json
{
  "status": "ok",
  "database": {"status": "connected", "type": "postgresql"},
  "storage": {"backend": "s3", "bucket": "interviewiq-prod"},
  "workers": "disabled",
  "deploy_mode": "remote"
}
```

### Worker Process
- Logs to stdout/stderr (captured by Render)
- Graceful shutdown on SIGTERM/SIGINT

---

## Rollback Procedure

### Database
```bash
# If migration fails, restore from backup
pg_restore -d $DATABASE_URL backup.dump

# Or if using Render: use Point-in-Time Recovery
```

### Application
```bash
# Render: redeploy previous commit
# Or: git revert <bad-commit> && push
```

### Configuration
- All config via environment variables
- Rollback = deploy previous env var set

---

## Known Limitations

1. **Rate Limiting**: In-memory only (per-instance). Not distributed across multiple web instances.
2. **WebSocket**: Live interview uses WebSockets - requires sticky sessions or Redis pub/sub for horizontal scaling.
3. **Gmail Polling**: Single worker only - not HA.
4. **File Uploads**: Local storage only in dev; S3 in production.
5. **SQLite**: Not suitable for multi-instance production.

---

## Security Checklist

- [ ] All secrets in environment variables (not code)
- [ ] `AUTH_SECRET` generated securely
- [ ] CORS restricted to `FRONTEND_ORIGIN`
- [ ] S3 bucket not public
- [ ] Database not publicly accessible
- [ ] OAuth redirect URIs exactly match registered values
- [ ] `client_secret.json` not in repo
- [ ] `settings.json` not in repo
- [ ] HTTPS enforced in production
- [ ] Rate limiting on auth endpoints

---

## Monitoring & Alerting

### Render Built-in
- CPU/Memory metrics
- Request latency
- Error rates
- Deploy status

### Application Logs
- Structured JSON logging (configure in production)
- Key events: screening completed, emails sent, errors

### Custom Health Checks
- Database connectivity
- S3 accessibility
- Gmail/Calendar API reachability
- Worker process alive

---

## Scaling Considerations

### Horizontal Scaling (Web)
- Add more web service instances
- Requires: Redis for rate limiting, WebSocket pub/sub
- Database connection pooling (pgbouncer)

### Worker Scaling
- Single worker per queue (screening, outbox, Gmail)
- Can run multiple workers with different queue partitions
- Idempotency ensures safe duplicate processing

### Database
- Read replicas for reporting queries
- Connection pooling (pgbouncer recommended)
- Partition large tables (screening_results, application_events)

---

## Support Contacts

- **Infrastructure**: Render Dashboard
- **Database**: Render PostgreSQL logs
- **Storage**: AWS S3 / MinIO / Cloudflare R2 console
- **OAuth**: Google Cloud Console / LinkedIn Developer Portal