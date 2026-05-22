#!/usr/bin/env bash
# scripts/auto_restart_services.sh
#
# Automated service recovery script.
# Monitors key processes (WebSocket client, Dash server) and restarts them
# if they die. Sends alert to Nav if restart fails 3 times.
#
# Usage:
#   ./scripts/auto_restart_services.sh [--daemon] [--check-interval SECONDS]
#
# Designed to be run as a cron job or systemd service.
# Recommended: */1 * * * * /path/to/auto_restart_services.sh

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_PYTHON="$BACKEND_DIR/venv/bin/python"
LOG_FILE="$PROJECT_DIR/logs/auto_restart.log"
STATE_DIR="$PROJECT_DIR/.auto_restart_state"
ALERT_EMAIL="${ALERT_EMAIL:-nav@example.com}"
MAX_RESTART_ATTEMPTS=3
RESTART_COOLDOWN_S=60
CHECK_INTERVAL_S=30

# Process definitions: name|start_command|health_check_url
declare -a SERVICES=(
    "dash_server|$VENV_PYTHON -m server --port 8050|http://localhost:8050/health"
    "websocket_client|$VENV_PYTHON -m services.schwab_streamer|"
)

# ── Setup ────────────────────────────────────────────────────────────────

mkdir -p "$(dirname "$LOG_FILE")" "$STATE_DIR"

log() {
    local level="$1"
    shift
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" | tee -a "$LOG_FILE"
}

# ── Process management ───────────────────────────────────────────────────

get_pid_file() {
    echo "$STATE_DIR/${1}.pid"
}

get_restart_count_file() {
    echo "$STATE_DIR/${1}.restart_count"
}

get_last_restart_file() {
    echo "$STATE_DIR/${1}.last_restart"
}

is_process_running() {
    local pid_file
    pid_file="$(get_pid_file "$1")"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

is_healthy() {
    local name="$1"
    local health_url=""
    for service in "${SERVICES[@]}"; do
        IFS='|' read -r sname _ shealth <<< "$service"
        if [[ "$sname" == "$name" ]]; then
            health_url="$shealth"
            break
        fi
    done

    if [[ -z "$health_url" ]]; then
        # No health check URL — just check if process is running
        return 0
    fi

    if curl -sf "$health_url" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

get_restart_count() {
    local file
    file="$(get_restart_count_file "$1")"
    if [[ -f "$file" ]]; then
        cat "$file"
    else
        echo 0
    fi
}

increment_restart_count() {
    local count
    count=$(get_restart_count "$1")
    echo $((count + 1)) > "$(get_restart_count_file "$1")"
}

reset_restart_count() {
    echo 0 > "$(get_restart_count_file "$1")"
}

get_last_restart_time() {
    local file
    file="$(get_last_restart_file "$1")"
    if [[ -f "$file" ]]; then
        cat "$file"
    else
        echo 0
    fi
}

set_last_restart_time() {
    date +%s > "$(get_last_restart_file "$1")"
}

can_restart() {
    local name="$1"
    local last_restart
    last_restart=$(get_last_restart_time "$name")
    local now
    now=$(date +%s)
    local elapsed=$((now - last_restart))

    if [[ $elapsed -lt $RESTART_COOLDOWN_S ]]; then
        log "WARN" "Cooldown active for $name (${elapsed}s < ${RESTART_COOLDOWN_S}s)"
        return 1
    fi
    return 0
}

# ── Service control ──────────────────────────────────────────────────────

start_service() {
    local name="$1"
    local cmd=""
    for service in "${SERVICES[@]}"; do
        IFS='|' read -r sname scmd _ <<< "$service"
        if [[ "$sname" == "$name" ]]; then
            cmd="$scmd"
            break
        fi
    done

    if [[ -z "$cmd" ]]; then
        log "ERROR" "Unknown service: $name"
        return 1
    fi

    log "INFO" "Starting $name: $cmd"

    # Start in background, save PID
    cd "$BACKEND_DIR"
    nohup bash -c "$cmd" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$(get_pid_file "$name")"

    # Wait for startup
    sleep 2

    if kill -0 "$pid" 2>/dev/null; then
        log "INFO" "$name started (PID: $pid)"
        return 0
    else
        log "ERROR" "$name failed to start"
        return 1
    fi
}

stop_service() {
    local name="$1"
    local pid_file
    pid_file="$(get_pid_file "$name")"

    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "INFO" "Stopping $name (PID: $pid)"
            kill "$pid" 2>/dev/null || true
            sleep 2
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                log "WARN" "Force killing $name (PID: $pid)"
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
}

restart_service() {
    local name="$1"

    if ! can_restart "$name"; then
        return 1
    fi

    increment_restart_count "$name"
    set_last_restart_time "$name"

    local count
    count=$(get_restart_count "$name")

    log "WARN" "Restarting $name (attempt $count/$MAX_RESTART_ATTEMPTS)"

    stop_service "$name"
    sleep 1

    if start_service "$name"; then
        log "INFO" "$name restarted successfully"
        return 0
    else
        log "ERROR" "$name restart failed (attempt $count/$MAX_RESTART_ATTEMPTS)"

        if [[ $count -ge $MAX_RESTART_ATTEMPTS ]]; then
            send_alert "$name" "$count"
        fi
        return 1
    fi
}

# ── Alerting ─────────────────────────────────────────────────────────────

send_alert() {
    local name="$1"
    local fail_count="$2"

    log "CRITICAL" "ALERT: $name failed $fail_count times — manual intervention required"

    # Try multiple alert methods
    # 1. Email (if mail command available)
    if command -v mail >/dev/null 2>&1; then
        echo "Service $name on $(hostname) has failed $fail_count restart attempts.
Please check immediately.

Log: $LOG_FILE
Time: $(date)

— Floww Auto-Restart" | mail -s "[FLOWW] Service Alert: $name" "$ALERT_EMAIL" 2>/dev/null || true
    fi

    # 2. Write to alert file for monitoring systems
    local alert_file="$STATE_DIR/alert_$(date +%Y%m%d_%H%M%S).txt"
    cat > "$alert_file" <<EOF
SERVICE_ALERT
service: $name
host: $(hostname)
time: $(date -u +%Y-%m-%dT%H:%M:%SZ)
fail_count: $fail_count
log_file: $LOG_FILE
EOF

    log "INFO" "Alert written to $alert_file"
}

# ── Health check loop ────────────────────────────────────────────────────

check_all_services() {
    local all_ok=true

    for service in "${SERVICES[@]}"; do
        IFS='|' read -r name _ _ <<< "$service"

        if is_process_running "$name"; then
            if is_healthy "$name"; then
                # Service healthy — reset restart count on success
                local count
                count=$(get_restart_count "$name")
                if [[ $count -gt 0 ]]; then
                    reset_restart_count "$name"
                    log "INFO" "$name is healthy — reset restart count"
                fi
            else
                log "WARN" "$name running but unhealthy"
                if ! restart_service "$name"; then
                    all_ok=false
                fi
            fi
        else
            log "WARN" "$name is not running"
            if ! restart_service "$name"; then
                all_ok=false
            fi
        fi
    done

    return 0
}

# ── Main ─────────────────────────────────────────────────────────────────

run_daemon() {
    log "INFO" "Auto-restart daemon starting (check interval: ${CHECK_INTERVAL_S}s)"
    log "INFO" "Monitoring services: $(echo "${SERVICES[@]}" | tr ' ' ',')"

    while true; do
        check_all_services || true
        sleep "$CHECK_INTERVAL_S"
    done
}

run_once() {
    log "INFO" "Running one-time health check"
    check_all_services
    local exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        log "INFO" "All services healthy"
    else
        log "WARN" "Some services had issues — check log for details"
    fi

    return $exit_code
}

# ── CLI ──────────────────────────────────────────────────────────────────

main() {
    local daemon=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --daemon)
                daemon=true
                shift
                ;;
            --check-interval)
                CHECK_INTERVAL_S="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: $0 [--daemon] [--check-interval SECONDS]"
                echo ""
                echo "Options:"
                echo "  --daemon           Run in continuous monitoring mode"
                echo "  --check-interval   Seconds between checks (default: 30)"
                echo "  --help             Show this help"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [[ "$daemon" == true ]]; then
        run_daemon
    else
        run_once
    fi
}

main "$@"
