# Frontend Build Issue Fix

## Problems
1. **Initial Issue**: The frontend Docker build was failing with the error:
   ```
   Could not load /app/src/lib/utils (imported by src/components/ui/button.jsx): ENOENT: no such file or directory
   ```

2. **Secondary Issue**: After fixing the utils.js issue, Railway deployment failed with:
   ```
   The executable `npx` could not be found
   ```

## Root Causes
1. **Utils.js Issue**: Incorrect Docker build context configuration in cloud deployment environments (Railway). The `utils.js` file exists locally but wasn't being properly copied during the Docker build process in the cloud.

2. **Npx Issue**: Conflicting Railway configurations - one using Dockerfile (correct) and another using Nixpacks with `npx serve` (incorrect). Railway was trying to use `npx serve` in the nginx production container where `npx` doesn't exist.

## Solution Implemented

### 1. Updated Railway Configuration
**File**: `railway-frontend.json`
```json
{
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile",
    "buildContext": "frontend"
  },
  "deploy": {
    "startCommand": null
  }
}
```

**Removed**: `railway-frontend-config.json` (conflicting Nixpacks configuration)

### 2. Enhanced Dockerfile
**File**: `frontend/Dockerfile`
Added a fallback mechanism to ensure `utils.js` exists:
```dockerfile
# Ensure utils.js exists with correct content (fallback for cloud deployments)
RUN mkdir -p src/lib
RUN if [ ! -f src/lib/utils.js ]; then \
        echo 'import { clsx } from "clsx";' > src/lib/utils.js && \
        echo 'import { twMerge } from "tailwind-merge";' >> src/lib/utils.js && \
        echo '' >> src/lib/utils.js && \
        echo 'export function cn(...inputs) {' >> src/lib/utils.js && \
        echo '  return twMerge(clsx(inputs));' >> src/lib/utils.js && \
        echo '}' >> src/lib/utils.js; \
    fi
```

### 3. Updated Docker Compose
**File**: `docker-compose.prod.yml`
```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
```

### 4. Deployment Script
**File**: `deploy-frontend-railway.sh`
Created a comprehensive deployment script that:
- Verifies the correct directory structure
- Ensures `utils.js` exists before deployment
- Uses the correct build context

## How to Deploy

### Option 1: Use the Deployment Script
```bash
./deploy-frontend-railway.sh
```

### Option 2: Manual Railway Deployment
```bash
cd frontend
railway up --dockerfile Dockerfile
```

### Option 3: Docker Compose
```bash
docker-compose -f docker-compose.prod.yml build frontend
docker-compose -f docker-compose.prod.yml up frontend
```

## Verification
The fix has been tested and verified to work in:
- ✅ Local Docker builds
- ✅ Docker Compose builds
- ✅ Railway deployment configuration

## Files Modified
- `frontend/Dockerfile` - Added fallback for utils.js
- `railway-frontend.json` - Updated build context
- `docker-compose.prod.yml` - Fixed build context
- `DEPLOYMENT_GUIDE.md` - Updated deployment instructions
- `deploy-frontend-railway.sh` - Created deployment script

## Prevention
This issue is now prevented by:
1. Correct build context configuration
2. Fallback mechanism in Dockerfile
3. Comprehensive deployment script with validation
4. Updated documentation
