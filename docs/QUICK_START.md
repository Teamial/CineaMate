# Quick Start Guide 🚀

## Starting the Application

You have multiple options to start the entire application stack (Docker DB + Backend + Frontend):

### Option 1: Using the start script (recommended)
```bash
./start.sh
```

### Option 2: Using npm
```bash
npm start
```

This will:
1. 📦 Start the PostgreSQL database in Docker
2. ⏳ Wait for the database to be ready
3. 🚀 Start the FastAPI backend on http://localhost:8000
4. 🎨 Start the React frontend on http://localhost:5173

## Stopping the Application

To stop all services gracefully:

### Option 1: If services are running in foreground
Press `Ctrl+C` in the terminal where you ran `./start.sh`

### Option 2: Using the stop script
```bash
./stop.sh
```

### Option 3: Using npm
```bash
npm stop
```

This will:
1. ⏹️  Stop the backend and frontend servers
2. 📦 Stop and remove Docker containers

## Restarting the Application

To restart all services at once:

```bash
./restart.sh
# or
npm run restart
```

## Useful URLs

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative API Docs**: http://localhost:8000/redoc

## Troubleshooting

### Port already in use
If you get a "port already in use" error:
```bash
./stop.sh  # This will kill any lingering processes
./start.sh  # Start fresh
```

### Database connection issues
If the backend can't connect to the database:
```bash
docker-compose down -v  # Remove volumes
docker-compose up -d     # Restart with fresh database
```

### Virtual environment not found
Make sure you have a Python virtual environment set up:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Development Workflow

1. **First time setup**: Make sure Docker is running and your virtual environment is set up
2. **Daily development**: Just run `./start.sh` - it handles everything!
3. **Done for the day**: Press `Ctrl+C` or run `./stop.sh`
4. **Making changes**: The backend and frontend both have hot-reload enabled!

---

Happy coding! 🎬✨
