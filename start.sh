#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "========================================"
echo "  AgentIR — Backend + Frontend Launcher"
echo "========================================"
echo ""

# ---- Backend ----
echo "[1/2] Starting backend (http://localhost:8000)..."
cd "$ROOT"
python3 -c "
from agentir.server.main import create_app
import uvicorn
uvicorn.run(create_app(), host='127.0.0.1', port=8000, log_level='info')
" &
BACKEND_PID=$!
sleep 2

# Quick health check
if curl -s http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    echo "      Backend is ready."
else
    echo "      ⚠ Backend health check failed — it may still be starting."
fi

# ---- Frontend ----
echo "[2/2] Starting frontend (http://localhost:5173)..."
cd "$ROOT/ui"
npm run dev -- --host 2>&1 &
FRONTEND_PID=$!
sleep 3

echo ""
echo "========================================"
echo "  Both services are starting up"
echo ""
echo "  Backend  → http://localhost:8000"
echo "  Swagger  → http://localhost:8000/docs"
echo "  Frontend → http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop all services."
echo "========================================"
echo ""

wait
