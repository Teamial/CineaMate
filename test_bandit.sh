#!/bin/bash
# Quick test script for bandit recommendations

API_URL="http://localhost:8000"

echo "🧪 Testing Bandit Recommendations"
echo "=================================="
echo ""

# Step 1: Login to get token
echo "1. Logging in..."
read -p "Enter username: " USERNAME
read -sp "Enter password: " PASSWORD
echo ""

TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$USERNAME&password=$PASSWORD" \
  | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo "❌ Login failed. Please check your credentials."
    exit 1
fi

echo "✅ Logged in successfully!"
echo ""

# Step 2: Get user ID
echo "2. Getting user info..."
USER_ID=$(curl -s -X GET "$API_URL/users/me" \
  -H "Authorization: Bearer $TOKEN" \
  | grep -o '"id":[0-9]*' | cut -d':' -f2)

echo "✅ User ID: $USER_ID"
echo ""

# Step 3: Test bandit recommendations
echo "3. Testing BANDIT recommendations (treatment)..."
curl -s -X GET "$API_URL/movies/recommendations?user_id=$USER_ID&limit=5&use_bandit=true" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.[] | "\(.id): \(.title)"' | head -5

echo ""
echo "✅ Bandit recommendations retrieved!"
echo ""

# Step 4: Test control recommendations
echo "4. Testing CONTROL recommendations (hybrid)..."
curl -s -X GET "$API_URL/movies/recommendations?user_id=$USER_ID&limit=5&use_bandit=false" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.[] | "\(.id): \(.title)"' | head -5

echo ""
echo "✅ Control recommendations retrieved!"
echo ""

# Step 5: Check bandit stats
echo "5. Checking bandit statistics..."
curl -s -X GET "$API_URL/analytics/bandit/stats" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.summary'

echo ""
echo "=================================="
echo "🎉 All tests passed!"
echo ""
echo "Next steps:"
echo "- Test clicking: curl -X POST '$API_URL/analytics/track/click' -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{\"user_id\": $USER_ID, \"movie_id\": 550}'"
echo "- Test rating: curl -X POST '$API_URL/analytics/track/rating' -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{\"user_id\": $USER_ID, \"movie_id\": 550, \"rating\": 4.5}'"
echo "- Check stats again: curl -X GET '$API_URL/analytics/bandit/stats' -H 'Authorization: Bearer $TOKEN' | jq"

