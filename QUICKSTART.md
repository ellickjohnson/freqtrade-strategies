# Quick Start Guide - Freqtrade Dashboard

## Status

✅ **Dashboard** is running on http://localhost:3001
✅ **Manager API** is running on port 8000
✅ **WebSocket** is running on port 8765
⚠️ **Docker Integration** is in limited mode (container management disabled)

## Current Issues

### Docker Socket Access

The manager service is running but cannot access Docker to spawn strategy containers. This is due to the Docker socket access issue inside the container. The API and dashboard still work, you just won't be able to start/stop strategies directly from the UI.

**Solutions:**

1. **Run manager on host** (recommended for development):
```bash
# Stop the manager container
docker compose stop manager

# Run manager locally
cd freqtrade_manager
python main.py
```

2. **Fix Docker socket permissions**:
```bash
# Add your user to docker group (requires relogin)
sudo usermod -aG docker $USER

# Or run with elevated privileges
docker compose down
docker compose up -d
```

## What's Working

### Dashboard (http://localhost:3001)
- ✅ Portfolio summary view
- ✅ Strategy cards display
- ✅ Real-time UI updates
- ✅ Template management buttons
- ⚠️ Start/Stop strategies (limited - see above)

### Manager API (http://localhost:8000)
- ✅ REST API for strategies
- ✅ Templates listing
- ✅ Portfolio aggregation
- ✅ WebSocket server
- ⚠️ Container management (limited)

## Accessing the Dashboard

1. **Open your browser**: http://localhost:3001

2. **Expected view**:
   - Portfolio P&L (empty - no running strategies)
   - "No strategies found" message
   - "Create Strategy" button

3. **Create a strategy** (requires Docker access):
   - Click "New Strategy"
   - Select a template
   - Configure parameters
   - Click "Create"

4. **Manual strategy creation** (workaround):
   - Create config file in `config/`
   - Restart the stack: `docker compose restart`
   - Dashboard will auto-detect on next startup

## Available Endpoints

### REST API
- `GET http://localhost:8000/health` - Health check
- `GET http://localhost:8000/api/strategies` - List strategies
- `GET http://localhost:8000/api/templates` - List templates
- `GET http://localhost:8000/api/portfolio` - Portfolio summary
- `POST http://localhost:8000/api/strategies` - Create strategy
- `POST http://localhost:8000/api/strategies/:id/start` - Start strategy
- `POST http://localhost:8000/api/strategies/:id/stop` - Stop strategy

### WebSocket
- `ws://localhost:8765` - Real-time updates

## Logs

```bash
# Manager logs
docker compose logs manager -f

# Dashboard logs
docker compose logs dashboard -f

# All logs
docker compose logs -f
```

## Next Steps

1. **Fix Docker access** to enable full functionality
2. **Configure Slack webhook** in `.env` for notifications
3. **Add existing strategies** by placing configs in `config/` directory
4. **Visit the dashboard** at http://localhost:3001

## Stopping the Stack

```bash
docker compose down
```