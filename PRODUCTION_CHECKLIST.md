# InterviewIQ Production Checklist

## Pre-Deployment

### Infrastructure
- [ ] Render account created
- [ ] PostgreSQL database provisioned
- [ ] S3-compatible storage bucket created
- [ ] Domain names configured (frontend + backend)
- [ ] SSL certificates configured (auto via Render/Vercel)

### OAuth Providers
- [ ] Google Cloud project created
- [ ] Gmail API enabled
- [ ] Calendar API enabled
- [ ] Gmail OAuth redirect URI registered
- [ ] Calendar OAuth redirect URI registered
- [ ] LinkedIn Developer app created
- [ ] LinkedIn products configured (Sign In + Share)
- [ ] LinkedIn OAuth redirect URI registered

### Secrets Management
- [ ] `AUTH_SECRET` generated (`openssl rand -hex 32`)
- [ ] `GROQ_API_KEY` obtained (if using LLM)
- [ ] `DATABASE_URL` configured
- [ ] S3 credentials stored securely
- [ ] LinkedIn client secret stored securely
- [ ] All secrets in environment variables (not code)

---

## Deployment

### Database Migration
- [ ] Local SQLite data backed up
- [ ] Migration script run: `python scripts/migrate_sqlite_to_pg.py`
- [ ] Row counts verified between SQLite and PostgreSQL
- [ ] Foreign key constraints validated
- [ ] Indexes created successfully

### Backend (Render Web Service)
- [ ] Repository connected to Render
- [ ] Build command: `pip install -r requirements.txt`
- [ ] Start command: `DEPLOY_MODE=remote INTERVIEWIQ_DISABLE_WORKERS=1 uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- [ ] Environment variables configured
- [ ] Health check path: `/health`
- [ ] Auto-deploy enabled
- [ ] Service accessible at backend domain

### Worker (Render Worker Service)
- [ ] Same repository connected
- [ ] Build command: `pip install -r requirements.txt`
- [ ] Start command: `python -m app.workers`
- [ ] Environment variables configured (same as web + `INTERVIEWIQ_DISABLE_WORKERS=0`)
- [ ] Auto-deploy enabled
- [ ] Logs visible in Render dashboard

### Frontend (Vercel)
- [ ] Repository connected to Vercel
- [ ] Build command: `npm run build`
- [ ] Output directory: `frontend/out`
- [ ] Environment variables: `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_API_URL`
- [ ] Rewrites configured for API proxy
- [ ] Deployed to frontend domain

### Electron (Desktop)
- [ ] `backend_mode: "remote"` configured
- [ ] `remote_api_url` set to backend domain
- [ ] `INTERVIEWIQ_DEFAULT_REMOTE_URL` set at build time
- [ ] Auto-update configured (GitHub Releases/S3)
- [ ] Installer built and tested

---

## Post-Deployment Verification

### Health Checks
- [ ] `GET https://api.yourdomain.com/health` returns `status: "ok"`
- [ ] Database shows `connected` + `type: "postgresql"`
- [ ] Storage shows correct backend + bucket
- [ ] Workers show `disabled` (web) / running (worker)

### API Functionality
- [ ] Recruiter login works
- [ ] Job creation works
- [ ] Public apply page loads
- [ ] Candidate flow works (invite → interview → complete)
- [ ] Screening pipeline processes applications
- [ ] Email invitations sent via Gmail
- [ ] Calendar scheduling works
- [ ] LinkedIn posting works
- [ ] File uploads (resumes, recordings) work
- [ ] Signed media URLs work
- [ ] Reports generate correctly

### OAuth Flows
- [ ] Gmail connect/disconnect works
- [ ] Calendar connect/disconnect works
- [ ] LinkedIn connect/disconnect works
- [ ] Redirect URIs match exactly (no trailing slashes)
- [ ] Tokens stored securely (not in frontend)

### Background Workers
- [ ] Screening jobs process (check logs)
- [ ] Outbox emails send (check Gmail sent folder)
- [ ] Gmail polling runs every 10 min (remote mode)
- [ ] No duplicate emails on retry
- [ ] Failed jobs visible in DB for inspection

### File Storage
- [ ] Resumes upload to S3
- [ ] Recordings upload to S3
- [ ] Presigned URLs work for media access
- [ ] Local dev still uses filesystem

---

## Security Verification

- [ ] CORS restricted to `FRONTEND_ORIGIN` only
- [ ] No `localhost` in production CORS
- [ ] `AUTH_SECRET` not exposed in frontend
- [ ] OAuth tokens not in API responses
- [ ] S3 bucket not public
- [ ] Database not publicly accessible
- [ ] Rate limiting on auth endpoints
- [ ] File upload size limits enforced
- [ ] Path traversal protection on media endpoint
- [ ] HTTPS enforced everywhere

---

## Performance Baseline

- [ ] API response times < 500ms (p95)
- [ ] Health check < 100ms
- [ ] Database queries optimized (no N+1)
- [ ] S3 upload/download speeds acceptable
- [ ] Worker processing keeps up with load

---

## Monitoring & Alerts

- [ ] Render health checks configured
- [ ] Error rate alerts (< 1%)
- [ ] Latency alerts (p95 > 1s)
- [ ] Worker lag alerts (queue depth > 100)
- [ ] Database connection pool alerts
- [ ] S3 error rate alerts

---

## Documentation

- [ ] `DEPLOYMENT_READINESS.md` reviewed
- [ ] Runbook for common operations
- [ ] Rollback procedure documented
- [ ] Team knows deployment process
- [ ] On-call rotation established

---

## Rollback Plan

### Quick Rollback (Code)
```bash
# Render: Click "Rollback" on previous deploy
# Or: git revert <bad-commit> && git push
```

### Database Rollback
```bash
# Option 1: Point-in-time recovery (Render)
# Option 2: Restore from pg_dump
pg_restore -d $DATABASE_URL backup.dump
```

### Configuration Rollback
```bash
# Revert environment variables in Render dashboard
# Redeploy
```

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| DevOps | | | |
| Backend Lead | | | |
| Frontend Lead | | | |
| Security | | | |

---

## Final GO/NO-GO

**GO** if all items checked ✅

**NO-GO** if any critical item unchecked ❌

### Critical Items (must pass)
- [ ] Database migration successful
- [ ] Health endpoint returns OK
- [ ] All OAuth flows work
- [ ] Background workers process jobs
- [ ] File storage works
- [ ] No secrets in code/repo
- [ ] HTTPS enforced
- [ ] CORS configured correctly

### Verdict: ___ GO / ___ NO-GO

**Date:** ___________ **Approved by:** ___________