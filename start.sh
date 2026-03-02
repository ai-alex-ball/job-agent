#!/usr/bin/env bash
# start.sh — launch the Job Agent approval server
# Usage: bash ~/job-agent/start.sh

set -e
cd "$(dirname "$0")"

# Kill any previous instance that's still running
if [ -f .approvals.pid ]; then
    OLD_PID=$(cat .approvals.pid)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping previous approval server (PID $OLD_PID)..."
        kill "$OLD_PID"
    fi
    rm -f .approvals.pid
fi

# Start the approval webhook server in the background
python3 approvals.py &
echo $! > .approvals.pid

echo ""
echo "  Job agent running — approval server on localhost:5000"
echo "  PID $(cat .approvals.pid) saved to .approvals.pid"
echo "  To stop: kill \$(cat ~/job-agent/.approvals.pid)"
echo ""
