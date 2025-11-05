# Railway Deployment Troubleshooting Guide

## Quick Diagnosis

### Symptom: Still seeing port 8080 in logs
```
[INFO] Listening at: http://0.0.0.0:8080 (1)
```

**Diagnosis:** Nixpacks is not reading nixpacks.toml

**Solutions:**
1. Verify nixpacks.toml is in the `api/` directory (same level as app.py)
2. Check Railway Settings → Root Directory is set to `api`
3. Force rebuild: Railway Dashboard → Deployments → Redeploy

### Symptom: Container stops after 3 seconds
```
[INFO] Booting worker with pid: 4
[INFO] Handling signal: term
[INFO] Shutting down: Master
```

**Diagnosis:** Health check failing due to port mismatch

**Solutions:**
1. Verify nixpacks.toml contains `$PORT` in the bind command
2. Check Railway logs for the actual assigned port
3. Ensure no hardcoded PORT=8080 in Railway environment variables

### Symptom: 502 Bad Gateway
**Diagnosis:** Railway can't reach the application on the assigned port

**Solutions:**
1. Check gunicorn is binding to 0.0.0.0 (not 127.0.0.1)
2. Verify $PORT is being passed to gunicorn
3. Check timeout setting (increase to 120s)

### Symptom: Module not found errors
```
ModuleNotFoundError: No module named 'flask'
```

**Diagnosis:** Dependencies not installed

**Solutions:**
1. Verify requirements.txt exists in api/ directory
2. Check Railway build logs for pip install errors
3. Add to nixpacks.toml: `cmds = ["pip install -r requirements.txt"]`

### Symptom: Database is locked
```
sqlite3.OperationalError: database is locked
```

**Diagnosis:** SQLite concurrency issues

**Solutions:**
1. Reduce workers to 1: `--workers 1`
2. Consider migrating to PostgreSQL
3. Add WAL mode to database connection

## Railway Configuration Verification

### Correct Settings Checklist
- [ ] Root Directory: `api`
- [ ] Custom Start Command: (empty)
- [ ] Builder: NIXPACKS (automatic)
- [ ] No hardcoded PORT variable in environment

### Verify Files Exist
```bash
cd api
ls -la nixpacks.toml  # Should exist
ls -la Procfile       # Should exist
ls -la railway.json   # Should exist
ls -la app.py         # Should exist
ls -la requirements.txt # Should exist
```

### Verify File Contents

**nixpacks.toml:**
```toml
[start]
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"
```
Key: Must include `$PORT` variable

**Procfile:**
```
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```
Key: No `web:` prefix, includes `$PORT`

**railway.json:**
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```
Key: No `startCommand` in deploy section

## Log Analysis

### Successful Deployment Logs
```
Building...
  ✓ Installing Python packages
  ✓ Building with Nixpacks
  ✓ Pushing to Railway

Deploying...
  [INFO] Starting gunicorn 23.0.0
  [INFO] Listening at: http://0.0.0.0:34567 (1)  ← Good! Dynamic port
  [INFO] Using worker: sync
  [INFO] Booting worker with pid: 4
  ← Container keeps running
```

### Failed Deployment Logs
```
Building...
  ✓ Installing Python packages
  ✓ Building with Nixpacks
  ✓ Pushing to Railway

Deploying...
  [INFO] Starting gunicorn 23.0.0
  [INFO] Listening at: http://0.0.0.0:8080 (1)    ← Bad! Hardcoded port
  [INFO] Using worker: sync
  [INFO] Booting worker with pid: 4
  [INFO] Handling signal: term                     ← Container stopping
  [INFO] Shutting down: Master
  Stopping Container
```

## Testing Procedure

### 1. Local Test (Before Pushing)
```bash
cd api
export PORT=5000
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Then in another terminal:
```bash
curl http://localhost:5000/api/health
```

Expected: `{"status":"healthy",...}`

### 2. Railway Test (After Deploy)
```bash
curl https://hydropage-production.up.railway.app/api/health
```

Expected: Same JSON response

### 3. Full API Test Suite
```bash
# Health
curl https://hydropage-production.up.railway.app/api/health

# Stats
curl https://hydropage-production.up.railway.app/api/stats

# Plants list
curl "https://hydropage-production.up.railway.app/api/plants?limit=5"

# Search
curl "https://hydropage-production.up.railway.app/api/plants/search?q=coulee"
```

## Common Issues and Fixes

### Issue 1: Environment Variable Not Set
**Symptom:** $PORT expands to empty string

**Check:**
```bash
# In Railway logs, look for:
[INFO] Listening at: http://0.0.0.0: (1)  ← Missing port number
```

**Fix:** Railway should auto-set $PORT. If not:
1. Check Railway service type (should be "Web Service")
2. Manually set PORT in Railway variables (last resort)

### Issue 2: Nixpacks Using Wrong Python Version
**Symptom:** Build fails with Python version errors

**Fix:** Update nixpacks.toml:
```toml
[phases.setup]
nixPkgs = ["python39"]  # or python310, python311
```

### Issue 3: Gunicorn Not Found
**Symptom:** `gunicorn: command not found`

**Fix:** Ensure requirements.txt includes:
```
gunicorn>=21.2.0
```

### Issue 4: Flask Not Found
**Symptom:** `ModuleNotFoundError: No module named 'flask'`

**Fix:** Ensure requirements.txt includes:
```
Flask>=3.0.0
Flask-CORS>=4.0.0
```

### Issue 5: Database Not Found
**Symptom:** `no such table: licensing_status`

**Fix:** Ensure hydropage.db is committed to git:
```bash
git add api/hydropage.db
git commit -m "Add database file"
git push
```

### Issue 6: CORS Errors
**Symptom:** Browser shows CORS policy errors

**Check app.py:**
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app)  # This line must exist
```

**Fix:** Ensure Flask-CORS is in requirements.txt and imported

## Nuclear Options (Last Resort)

### Option 1: Delete and Recreate Service
1. Railway Dashboard → Settings → Delete Service
2. New → Deploy from GitHub
3. Select: amontbrun98/Hydropage
4. Root Directory: `api`
5. Deploy

### Option 2: Switch to Dockerfile
Create `api/Dockerfile`:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Railway Settings:
- Builder: Dockerfile
- Dockerfile Path: `api/Dockerfile`

### Option 3: Manual Start Command Override
Railway Settings → Deploy → Custom Start Command:
```
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

## Verification Commands

### Check Nixpacks Configuration
```bash
# Local test of nixpacks.toml syntax
cat api/nixpacks.toml

# Should see:
[start]
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"
```

### Check Railway Environment
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and link
railway login
railway link

# Check environment variables
railway variables

# Should NOT see PORT=8080 (let Railway auto-assign)
```

### Check Git Status
```bash
cd C:\xampp\htdocs\htdocs\Hydropage
git status

# Should show:
# On branch main
# Your branch is up to date with 'origin/main'
# nothing to commit, working tree clean
```

## Railway CLI Debugging

### Install Railway CLI
```bash
npm install -g @railway/cli
```

### Link to Project
```bash
cd C:\xampp\htdocs\htdocs\Hydropage
railway login
railway link
```

### Watch Logs Live
```bash
railway logs --follow
```

### Force Redeploy
```bash
railway up
```

### Check Service Info
```bash
railway status
```

## Port Binding Verification

### Correct Binding (What We Want)
```bash
gunicorn app:app --bind 0.0.0.0:$PORT
# Railway assigns PORT → gunicorn uses it
# Example: PORT=34567 → binds to 0.0.0.0:34567
```

### Incorrect Binding (What Was Happening)
```bash
gunicorn app:app
# No explicit port → defaults to 8080
# Railway expects 34567 → can't connect → 502 error
```

## Success Criteria

Your deployment is successful when ALL of these are true:
- ✅ Build completes without errors
- ✅ Deploy completes without errors
- ✅ Logs show "Listening at: http://0.0.0.0:XXXXX" (NOT 8080)
- ✅ Container stays running (no "Shutting down: Master")
- ✅ curl to /api/health returns JSON
- ✅ Browser shows API response (no 502)
- ✅ All test endpoints respond correctly

## Still Not Working?

### Gather Information
1. Screenshot Railway build logs
2. Screenshot Railway deploy logs
3. Copy nixpacks.toml contents
4. Copy railway.json contents
5. Note Railway settings (Root Directory, Environment Variables)

### Check Railway Status
- https://railway.app/status
- Check for any ongoing incidents

### Community Support
- Railway Discord: https://discord.gg/railway
- Railway Documentation: https://docs.railway.app/
- GitHub Issues: https://github.com/railwayapp/nixpacks/issues

## Rollback Plan

### If Deployment Breaks Something
1. Railway Dashboard → Deployments
2. Find last working deployment
3. Click "..." → Rollback
4. Service reverts to previous version

### If Need to Revert Changes
```bash
cd C:\xampp\htdocs\htdocs\Hydropage
git log  # Find commit before changes
git revert HEAD  # Undo last commit
git push
```

## Performance Optimization

### After Successful Deployment

**Increase Workers (if needed):**
```toml
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120"
```

**Add Thread Workers:**
```toml
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120"
```

**Production Settings:**
```toml
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -"
```

## Monitoring

### Railway Metrics
- CPU usage
- Memory usage
- Network traffic
- Response times

### Custom Monitoring
Add to requirements.txt:
```
sentry-sdk[flask]
```

Configure in app.py:
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FlaskIntegration()]
)
```

## Migration to PostgreSQL (Future)

Current: SQLite (single file, included in repo)
Future: PostgreSQL (Railway provides free tier)

**Steps:**
1. Railway Dashboard → New → Database → PostgreSQL
2. Copy DATABASE_URL from Railway
3. Install psycopg2: `pip install psycopg2-binary`
4. Update app.py to use DATABASE_URL
5. Migrate data from SQLite to PostgreSQL

## Contact Information

**Project Repository:**
https://github.com/amontbrun98/Hydropage

**Railway Project:**
https://railway.app/ (your project dashboard)

**Production URL:**
https://hydropage-production.up.railway.app

---

**Remember:** The key fix is the nixpacks.toml file with explicit $PORT binding!
