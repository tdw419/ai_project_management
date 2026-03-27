#!/bin/bash
#
# AIPM Continuous Loop Control Script
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOOP_SCRIPT="$SCRIPT_DIR/continuous_loop.py"
PID_FILE="$SCRIPT_DIR/.loop.pid"
LOG_FILE="$SCRIPT_DIR/logs/loop.log"

mkdir -p "$SCRIPT_DIR/logs"

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Loop already running (PID: $(cat "$PID_FILE"))"
        exit 1
    fi
    
    echo "Starting continuous loop..."
    source "$VENV/bin/activate"
    nohup python3 "$LOOP_SCRIPT" "$@" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started. PID: $(cat $PID_FILE)"
    echo "Logs: $LOG_FILE"
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "Stopping loop (PID: $PID)..."
        kill $PID 2>/dev/null
        rm -f "$PID_FILE"
        echo "Stopped."
    else
        echo "Loop not running."
    fi
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "✅ Loop running (PID: $PID)"
            echo ""
            echo "Recent logs:"
            tail -20 "$LOG_FILE"
        else
            echo "⚠️ Stale PID file (process not running)"
            rm -f "$PID_FILE"
        fi
    else
        echo "⚪ Loop not running"
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -100 "$LOG_FILE"
    else
        echo "No logs yet."
    fi
}

case "$1" in
    start)
        shift
        start "$@"
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        shift
        start "$@"
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs} [options]"
        echo ""
        echo "Commands:"
        echo "  start    - Start the continuous loop"
        echo "  stop     - Stop the continuous loop"
        echo "  restart  - Restart the loop"
        echo "  status   - Check if loop is running"
        echo "  logs     - View recent logs"
        echo ""
        echo "Options:"
        echo "  --interval N      Process every N seconds (default: 60)"
        echo "  --max N           Process max N prompts then stop"
        echo "  --project NAME    Only process prompts for this project"
        echo "  --pi              Use Pi agent with zai/glm-5 model"
        echo "  --pi-model MODEL  Use specific model for Pi agent"
        echo ""
        echo "Examples:"
        echo "  $0 start                              # LM Studio mode"
        echo "  $0 start --pi                         # Pi agent with zai/glm-5"
        echo "  $0 start --pi --pi-model qwen2.5-7b   # Pi agent with custom model"
        exit 1
        ;;
esac
