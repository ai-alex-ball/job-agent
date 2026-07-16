#!/usr/bin/env bash
# autostart.sh — used by Windows Task Scheduler via VBScript.
# Runs Flask in the FOREGROUND so that wsl.exe stays alive.
# (Backgrounding with & causes WSL to terminate the process when the session exits.)
#
# EDIT THIS: set to the absolute path of your job-agent clone
# (Windows Task Scheduler invokes this via wsl.exe with a fixed cwd, so it
# can't rely on $(dirname "$0") the way start.sh does).
cd /path/to/job-agent

# Kill any previous instance
if [ -f .approvals.pid ]; then
    old=$(cat .approvals.pid)
    if kill -0 "$old" 2>/dev/null; then
        kill "$old"
        sleep 1
    fi
    rm -f .approvals.pid
fi

# Save PID before exec — exec preserves the process ID
printf '%d\n' "$$" > .approvals.pid

# Replace this shell with python3.
# exec keeps wsl.exe alive until Flask exits.
exec python3 approvals.py >> logs/approvals.log 2>&1
