#!/bin/bash

# Test script to verify CORS fix for thumbs up/down feature
# This script tests the analytics endpoint that was failing with CORS errors

echo "🧪 Testing CORS fix for thumbs up/down feature..."
echo ""

BACKEND_URL="https://backend-production-003c.up.railway.app"
FRONTEND_URL="https://cineamate.up.railway.app"

echo "🔍 Testing CORS headers on analytics endpoint..."
echo "   Backend: $BACKEND_URL"
echo "   Frontend: $FRONTEND_URL"
echo ""

# Test the thumbs-status endpoint (the one that was failing)
echo "📡 Testing /analytics/thumbs-status/150540 endpoint..."

# Use curl to test CORS headers
CORS_TEST=$(curl -s -I -H "Origin: $FRONTEND_URL" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  "$BACKEND_URL/analytics/thumbs-status/150540" 2>/dev/null)

echo "Response headers:"
echo "$CORS_TEST" | grep -i "access-control\|origin\|http"

echo ""
echo "🔍 Checking for Access-Control-Allow-Origin header..."

if echo "$CORS_TEST" | grep -qi "access-control-allow-origin"; then
    echo "✅ Access-Control-Allow-Origin header found!"
    ALLOWED_ORIGIN=$(echo "$CORS_TEST" | grep -i "access-control-allow-origin" | sed 's/.*: *//' | tr -d ' \r\n')
    echo "   Allowed origin: $ALLOWED_ORIGIN"
    
    if [[ "$ALLOWED_ORIGIN" == "*" ]] || [[ "$ALLOWED_ORIGIN" == "$FRONTEND_URL" ]]; then
        echo "✅ CORS configuration looks correct!"
    else
        echo "⚠️  Allowed origin doesn't match frontend URL"
    fi
else
    echo "❌ Access-Control-Allow-Origin header not found!"
    echo "   This indicates the CORS fix may not have taken effect yet."
fi

echo ""
echo "🕐 Note: Railway deployments can take 1-2 minutes to complete."
echo "   If the test fails, wait a moment and try again."
echo ""
echo "🧪 Manual test instructions:"
echo "   1. Open https://cineamate.up.railway.app in your browser"
echo "   2. Log in to your account"
echo "   3. Go to recommendations or search for movies"
echo "   4. Try clicking the thumbs up/down buttons on any movie"
echo "   5. Check browser console (F12) for any CORS errors"
echo ""
echo "✅ If no CORS errors appear, the fix is working!"
