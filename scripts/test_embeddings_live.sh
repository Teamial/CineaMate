#!/bin/bash
# Live test of embedding-based recommendations

set -e

echo "🧪 Testing Embedding-Based Recommendations"
echo "=========================================="
echo ""

# Check server health
echo "1️⃣  Checking server health..."
HEALTH=$(curl -s http://localhost:8000/health)
echo "   $HEALTH"
echo ""

# Get username from user or use default
read -p "Enter username (or press Enter for 'secret'): " USERNAME
USERNAME=${USERNAME:-secret}

read -sp "Enter password (or press Enter for 'password'): " PASSWORD
PASSWORD=${PASSWORD:-password}
echo ""
echo ""

# Login and get token
echo "2️⃣  Logging in as '$USERNAME'..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=$USERNAME&password=$PASSWORD" 2>&1)

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo "   ❌ Login failed!"
    echo "   Response: $LOGIN_RESPONSE"
    echo ""
    echo "💡 Try these steps:"
    echo "   1. Check if user exists in database"
    echo "   2. Verify password is correct"
    echo "   3. Or create a new user first"
    echo ""
    exit 1
fi

echo "   ✅ Logged in successfully!"
echo "   Token: ${TOKEN:0:20}..."
echo ""

# Get user ID
echo "3️⃣  Getting user info..."
USER_INFO=$(curl -s http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN")
USER_ID=$(echo "$USER_INFO" | jq -r '.id' 2>/dev/null)
USERNAME_DISPLAY=$(echo "$USER_INFO" | jq -r '.username' 2>/dev/null)

if [ "$USER_ID" = "null" ] || [ -z "$USER_ID" ]; then
    echo "   ❌ Could not get user info"
    echo "   Response: $USER_INFO"
    exit 1
fi

echo "   ✅ User ID: $USER_ID ($USERNAME_DISPLAY)"
echo ""

# Test WITHOUT embeddings (baseline)
echo "4️⃣  Testing BASELINE recommendations (no embeddings)..."
echo "   Endpoint: /movies/recommendations?user_id=$USER_ID&limit=5&use_embeddings=false"
echo ""
BASELINE=$(curl -s "http://localhost:8000/movies/recommendations?user_id=$USER_ID&limit=5&use_embeddings=false" \
  -H "Authorization: Bearer $TOKEN")

if echo "$BASELINE" | jq -e '. | length' > /dev/null 2>&1; then
    echo "   ✅ Baseline recommendations:"
    echo "$BASELINE" | jq -r '.[] | "      \(.title) (\(.vote_average)/10)"'
else
    echo "   ⚠️  Response: $BASELINE"
fi
echo ""

# Test WITH embeddings
echo "5️⃣  Testing EMBEDDING-BASED recommendations (deep learning)..."
echo "   Endpoint: /movies/recommendations?user_id=$USER_ID&limit=5&use_embeddings=true"
echo ""
echo "   ⏱️  This may take 1-2 seconds on first run (loading models)..."
EMBEDDINGS=$(curl -s "http://localhost:8000/movies/recommendations?user_id=$USER_ID&limit=5&use_embeddings=true" \
  -H "Authorization: Bearer $TOKEN")

if echo "$EMBEDDINGS" | jq -e '. | length' > /dev/null 2>&1; then
    echo "   ✅ Embedding-based recommendations:"
    echo "$EMBEDDINGS" | jq -r '.[] | "      \(.title) (\(.vote_average)/10)"'
else
    echo "   ⚠️  Response: $EMBEDDINGS"
fi
echo ""

# Comparison
echo "6️⃣  Comparing results..."
BASELINE_COUNT=$(echo "$BASELINE" | jq -e '. | length' 2>/dev/null || echo 0)
EMBEDDINGS_COUNT=$(echo "$EMBEDDINGS" | jq -e '. | length' 2>/dev/null || echo 0)

echo "   Baseline returned: $BASELINE_COUNT movies"
echo "   Embeddings returned: $EMBEDDINGS_COUNT movies"
echo ""

if [ "$BASELINE_COUNT" -gt 0 ] && [ "$EMBEDDINGS_COUNT" -gt 0 ]; then
    echo "🎉 SUCCESS! Both recommendation methods working!"
    echo ""
    echo "📊 The embedding-based system uses:"
    echo "   • BERT for semantic text understanding"
    echo "   • ResNet50 for visual poster analysis"
    echo "   • User profile from viewing history"
    echo "   • Multi-modal fusion (70% text + 30% image)"
    echo ""
else
    echo "⚠️  Some recommendations may be missing"
fi

echo "✅ Test complete!"
echo ""
echo "💡 To test manually:"
echo "   export TOKEN='$TOKEN'"
echo "   curl \"http://localhost:8000/movies/recommendations?user_id=$USER_ID&limit=10&use_embeddings=true\" \\"
echo "     -H \"Authorization: Bearer \$TOKEN\" | jq '.'"
