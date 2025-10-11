#!/bin/bash

# Deploy frontend to Railway with correct build context
echo "🚀 Deploying frontend to Railway..."

# Check if we're in the right directory
if [ ! -f "frontend/Dockerfile" ]; then
    echo "❌ Error: frontend/Dockerfile not found. Please run this script from the project root."
    exit 1
fi

# Navigate to frontend directory for proper build context
cd frontend

# Verify utils.js exists
if [ ! -f "src/lib/utils.js" ]; then
    echo "⚠️  Warning: src/lib/utils.js not found. Creating it..."
    mkdir -p src/lib
    cat > src/lib/utils.js << 'EOF'
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
EOF
fi

# Deploy with correct build context
echo "🔧 Building and deploying with Railway..."
echo "📋 Using Dockerfile build method (not Nixpacks)"
railway up --dockerfile Dockerfile

echo "✅ Frontend deployment initiated!"
echo "📝 Note: Make sure to set VITE_API_URL environment variable in Railway dashboard"
echo "🔍 If build fails, check Railway logs for detailed error information"
