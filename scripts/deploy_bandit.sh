#!/bin/bash
# Bandit Selector Deployment Script
# Automates the deployment of Thompson Sampling bandit for A/B testing

set -e  # Exit on error

echo "============================================================"
echo "🎰 BANDIT SELECTOR DEPLOYMENT"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "📁 Project root: $PROJECT_ROOT"
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."

# Check Python
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python installed"

# Check DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo -e "${YELLOW}⚠️  DATABASE_URL not set in environment${NC}"
    
    # Try to load from .env
    if [ -f .env ]; then
        echo "   Loading from .env file..."
        export $(cat .env | grep DATABASE_URL | xargs)
    fi
    
    if [ -z "$DATABASE_URL" ]; then
        echo -e "${RED}❌ DATABASE_URL still not found${NC}"
        echo "   Please set DATABASE_URL environment variable"
        exit 1
    fi
fi
echo -e "${GREEN}✓${NC} DATABASE_URL configured"

# Check NumPy
if ! python -c "import numpy" &> /dev/null; then
    echo -e "${YELLOW}⚠️  NumPy not installed, installing...${NC}"
    pip install numpy
fi
echo -e "${GREEN}✓${NC} NumPy installed"

echo ""
echo "============================================================"
echo "Step 1: Database Migration"
echo "============================================================"
echo ""

# Run migration
echo "Running migration script..."
python backend/migrate_add_bandit_states.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Migration completed successfully"
else
    echo -e "${RED}❌ Migration failed${NC}"
    exit 1
fi

echo ""
echo "============================================================"
echo "Step 2: Verify Database Setup"
echo "============================================================"
echo ""

# Verify table exists
python -c "
from backend.database import SessionLocal
from backend.models import BanditState

db = SessionLocal()
try:
    count = db.query(BanditState).count()
    print(f'✓ BanditState table accessible (currently {count} records)')
except Exception as e:
    print(f'❌ Error accessing BanditState table: {e}')
    exit(1)
finally:
    db.close()
"

echo ""
echo "============================================================"
echo "Step 3: Test Bandit Selector"
echo "============================================================"
echo ""

# Test bandit selector
python -c "
from backend.database import SessionLocal
from backend.ml.bandit_selector import BanditSelector

db = SessionLocal()
try:
    bandit = BanditSelector(db)
    
    # Test context extraction
    context = bandit.extract_context(user_id=1)
    print(f'✓ Context extraction working: {context}')
    
    # Test arm selection
    algorithms, confidences = bandit.select_arms(context, n_arms=3)
    print(f'✓ Arm selection working: {list(zip(algorithms, confidences))}')
    
    # Test stats
    stats = bandit.get_bandit_stats()
    print(f'✓ Stats retrieval working: {len(stats)} state(s) found')
    
except Exception as e:
    print(f'❌ Bandit selector test failed: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    db.close()
"

echo ""
echo "============================================================"
echo "Step 4: Deployment Summary"
echo "============================================================"
echo ""

echo -e "${GREEN}✅ DEPLOYMENT SUCCESSFUL${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Restart API Server:"
echo "   Development: uvicorn backend.main:app --reload"
echo "   Production:  gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker"
echo ""
echo "2. Test Recommendations:"
echo "   curl -X GET \"http://localhost:8000/movies/recommendations?user_id=1&use_bandit=true\" \\"
echo "     -H \"Authorization: Bearer YOUR_TOKEN\""
echo ""
echo "3. Check Bandit Stats:"
echo "   curl -X GET \"http://localhost:8000/analytics/bandit/stats\" \\"
echo "     -H \"Authorization: Bearer YOUR_TOKEN\""
echo ""
echo "4. Monitor System:"
echo "   python backend/ml/monitoring_alerts.py"
echo ""
echo "5. View Documentation:"
echo "   cat BANDIT_DEPLOYMENT.md"
echo ""
echo "============================================================"
echo "🎉 Thompson Sampling Bandit is ready for A/B testing!"
echo "============================================================"
echo ""
echo "The system will now:"
echo "  • Automatically select best algorithms by context"
echo "  • Learn from user feedback (clicks, ratings, thumbs)"
echo "  • Optimize recommendations over time"
echo "  • Run daily monitoring at 9 AM"
echo ""
echo "Check progress:"
echo "  GET /analytics/bandit/stats"
echo "  GET /analytics/performance?days=7"
echo ""
echo "Happy testing! 🚀"

