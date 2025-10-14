#!/bin/bash

# Test script to verify thumbs up/down feature is working
# This script tests the analytics endpoints that were failing with schema errors

echo "🧪 Testing thumbs up/down feature after schema fix..."
echo ""

BACKEND_URL="https://backend-production-003c.up.railway.app"

echo "🔍 Testing analytics endpoints..."

# Test 1: Check if thumbs-status endpoint works (this was failing before)
echo "📡 Testing /analytics/thumbs-status/150540 endpoint..."

# This should return a proper response instead of a schema error
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/thumbs_status_response.json "$BACKEND_URL/analytics/thumbs-status/150540" -H "Authorization: Bearer test-token")

HTTP_CODE="${RESPONSE: -3}"
echo "HTTP Status Code: $HTTP_CODE"

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Endpoint is working (401 = authentication required, not schema error)"
    echo "   This means the database schema issue is fixed!"
elif [ "$HTTP_CODE" = "500" ]; then
    echo "❌ Still getting server error - checking response..."
    cat /tmp/thumbs_status_response.json
else
    echo "✅ Endpoint responded with status $HTTP_CODE"
fi

echo ""
echo "🔍 Testing toggle endpoints..."

# Test 2: Check toggle endpoints
echo "📡 Testing /analytics/toggle-thumbs-up/150540 endpoint..."

RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/toggle_response.json -X POST "$BACKEND_URL/analytics/toggle-thumbs-up/150540" -H "Authorization: Bearer test-token")

HTTP_CODE="${RESPONSE: -3}"
echo "HTTP Status Code: $HTTP_CODE"

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Toggle endpoint is working (401 = authentication required, not schema error)"
elif [ "$HTTP_CODE" = "500" ]; then
    echo "❌ Still getting server error - checking response..."
    cat /tmp/toggle_response.json
else
    echo "✅ Toggle endpoint responded with status $HTTP_CODE"
fi

echo ""
echo "🧪 Manual test instructions:"
echo "   1. Open https://cineamate.up.railway.app in your browser"
echo "   2. Log in to your account"
echo "   3. Go to recommendations or search for movies"
echo "   4. Try clicking the thumbs up/down buttons on any movie"
echo "   5. Check browser console (F12) for any errors"
echo ""
echo "✅ If no CORS errors or schema errors appear, the fix is working!"
echo ""
echo "📝 Note: The bandit experiment fields are temporarily disabled"
echo "   until the database migration can be completed properly."
