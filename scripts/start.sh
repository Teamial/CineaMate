#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Movie Recommender Application...${NC}\n"

# Step 1: Start Docker containers
echo -e "${YELLOW}📦 Starting Docker containers...${NC}"
docker-compose up -d

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to start Docker containers${NC}"
    exit 1
fi

# Wait for PostgreSQL to be healthy
echo -e "${YELLOW}⏳ Waiting for PostgreSQL to be ready...${NC}"
until docker exec movies-postgres pg_isready -U postgres > /dev/null 2>&1; do
    printf "."
    sleep 1
done
echo -e "\n${GREEN}✅ PostgreSQL is ready!${NC}\n"

# Step 2: Activate virtual environment and start backend + frontend
echo -e "${YELLOW}🎬 Starting Backend & Frontend servers...${NC}"
echo -e "${BLUE}Backend:${NC} http://localhost:8000"
echo -e "${BLUE}Frontend:${NC} http://localhost:5173"
echo -e "${BLUE}Docs:${NC} http://localhost:8000/docs"
echo -e "\n${GREEN}Press Ctrl+C to stop all services${NC}\n"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

# Trap Ctrl+C to run cleanup
trap 'echo -e "\n${YELLOW}🛑 Stopping all services...${NC}"; npm run stop-services 2>/dev/null || docker-compose down; echo -e "${GREEN}✅ All services stopped!${NC}"; exit 0' INT

# Start the services
npm run dev
