#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 Stopping Movie Recommender Application...${NC}\n"

# Step 1: Kill backend and frontend processes
echo -e "${YELLOW}⏹️  Stopping Backend & Frontend servers...${NC}"

# Find and kill uvicorn (backend) processes
BACKEND_PIDS=$(pgrep -f "uvicorn backend.main:app")
if [ ! -z "$BACKEND_PIDS" ]; then
    echo "Stopping backend processes: $BACKEND_PIDS"
    echo "$BACKEND_PIDS" | xargs kill -15 2>/dev/null
    sleep 2
    # Force kill if still running
    echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Find and kill vite (frontend) processes
FRONTEND_PIDS=$(pgrep -f "vite")
if [ ! -z "$FRONTEND_PIDS" ]; then
    echo "Stopping frontend processes: $FRONTEND_PIDS"
    echo "$FRONTEND_PIDS" | xargs kill -15 2>/dev/null
    sleep 2
    # Force kill if still running
    echo "$FRONTEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Find and kill node processes related to concurrently
NODE_PIDS=$(pgrep -f "concurrently")
if [ ! -z "$NODE_PIDS" ]; then
    echo "Stopping concurrently processes: $NODE_PIDS"
    echo "$NODE_PIDS" | xargs kill -15 2>/dev/null
    sleep 1
    echo "$NODE_PIDS" | xargs kill -9 2>/dev/null || true
fi

echo -e "${GREEN}✅ Backend & Frontend stopped!${NC}\n"

# Step 2: Stop Docker containers
echo -e "${YELLOW}📦 Stopping Docker containers...${NC}"
docker-compose down

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker containers stopped!${NC}\n"
else
    echo -e "${RED}❌ Failed to stop Docker containers${NC}\n"
    exit 1
fi

echo -e "${GREEN}🎉 All services stopped successfully!${NC}"
