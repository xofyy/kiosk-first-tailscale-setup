#!/bin/bash

#==============================================================================
# Display Monitor Script v4 (Final + Touchscreen)
# 
# Features:
#   - Cable connected/disconnected detection (xrandr)
#   - Screen on/off detection (ddcutil)
#   - Touchscreen USB detection (lsusb + xinput)
#   - Timestamped logging
#   - Session statistics
#   - Multiple instance protection
#   - Graceful shutdown
#
# Usage:
#   ./monitor-display.sh           Continuous monitoring
#   ./monitor-display.sh --status  One-time status check
#   ./monitor-display.sh --help    Help
#
# Requirements:
#   - xrandr
#   - ddcutil (for screen on/off detection)
#   - xinput (for touchscreen input detection)
#
#==============================================================================

set -o pipefail

#------------------------------------------------------------------------------
# CONFIGURATION
#------------------------------------------------------------------------------

DISPLAY_OUTPUT="DVI-D-0"
LOG_FILE="/var/log/aco-panel/display-monitor.log"
PID_FILE="/var/run/display-monitor.pid"
MAX_LOG_SIZE_MB=50

# Detect if running under systemd (INVOCATION_ID is set by systemd)
RUNNING_UNDER_SYSTEMD=false
if [ -n "${INVOCATION_ID:-}" ]; then
    RUNNING_UNDER_SYSTEMD=true
fi

# Touchscreen USB ID
TOUCH_USB_ID="222a:0001"
TOUCH_INPUT_NAME="ilitek"

# Check intervals (seconds)
CHECK_INTERVAL=5          # Cable & touchscreen check
DDC_CHECK_INTERVAL=15     # DDC check (slower to reduce system load)

# X11 environment variables
export DISPLAY=:0
export XAUTHORITY=/home/kiosk/.Xauthority

# NVIDIA driver check
NVIDIA_DRIVER_LOADED=false
if lsmod | grep -q "^nvidia "; then
    NVIDIA_DRIVER_LOADED=true
fi

#------------------------------------------------------------------------------
# COLOR CODES
#------------------------------------------------------------------------------

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' NC=''
fi

#------------------------------------------------------------------------------
# STATE VARIABLES
#------------------------------------------------------------------------------

PREV_CONNECTION=""
PREV_DDC_STATUS=""
PREV_TOUCH_STATUS=""
# Initialize to interval so first DDC check happens immediately
DDC_CHECK_COUNTER=$((DDC_CHECK_INTERVAL / CHECK_INTERVAL))
DDC_AVAILABLE=false

# Statistics
STAT_START_TIME=""
STAT_CABLE_DISCONNECT=0
STAT_CABLE_CONNECT=0
STAT_SCREEN_OFF=0
STAT_SCREEN_ON=0
STAT_TOUCH_DISCONNECT=0
STAT_TOUCH_CONNECT=0
STAT_TOUCH_ERROR=0

#------------------------------------------------------------------------------
# STATUS JSON FILE
#------------------------------------------------------------------------------

STATUS_JSON_FILE="/var/run/display-monitor.json"

write_status_json() {
    local curr_conn="$1"
    local curr_ddc="$2"
    local curr_touch="$3"
    local res="$4"
    local size="$5"

    # Calculate uptime
    local uptime_sec=0
    if [ -n "$STAT_START_TIME" ]; then
        local start_sec=$(date -d "$STAT_START_TIME" +%s 2>/dev/null || echo 0)
        local now_sec=$(date +%s)
        uptime_sec=$((now_sec - start_sec))
    fi

    # Build JSON
    local json_content
    json_content=$(cat <<EOF
{
  "timestamp": $(date +%s),
  "uptime_seconds": ${uptime_sec},
  "cable": {
    "status": "${curr_conn}",
    "resolution": "${res:--}",
    "physical_size": "${size:--}"
  },
  "screen": {
    "status": "${curr_ddc}",
    "ddc_available": ${DDC_AVAILABLE}
  },
  "nvidia_driver": ${NVIDIA_DRIVER_LOADED},
  "touchscreen": {
    "status": "${curr_touch}",
    "usb_id": "${TOUCH_USB_ID}"
  },
  "statistics": {
    "cable_connect": ${STAT_CABLE_CONNECT},
    "cable_disconnect": ${STAT_CABLE_DISCONNECT},
    "screen_on": ${STAT_SCREEN_ON},
    "screen_off": ${STAT_SCREEN_OFF},
    "touch_connect": ${STAT_TOUCH_CONNECT},
    "touch_disconnect": ${STAT_TOUCH_DISCONNECT},
    "touch_error": ${STAT_TOUCH_ERROR}
  }
}
EOF
)

    # Atomic write: write to temp file, then move
    local tmp_file="${STATUS_JSON_FILE}.tmp.$$"
    if echo "$json_content" > "$tmp_file" 2>/dev/null; then
        mv -f "$tmp_file" "$STATUS_JSON_FILE" 2>/dev/null || rm -f "$tmp_file"
    fi
}

cleanup_status_json() {
    rm -f "$STATUS_JSON_FILE" "${STATUS_JSON_FILE}.tmp."* 2>/dev/null
}

#------------------------------------------------------------------------------
# LOG FUNCTION
#------------------------------------------------------------------------------

log_event() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Write to log file (ignore errors to prevent script crash)
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE" 2>/dev/null || true
    
    # Terminal output
    case $level in
        "ERROR") echo -e "[$timestamp] [${RED}${BOLD}$level${NC}] $message" ;;
        "WARN")  echo -e "[$timestamp] [${YELLOW}$level${NC}] $message" ;;
        "INFO")  echo -e "[$timestamp] [${GREEN}$level${NC}] $message" ;;
        "DEBUG") echo -e "[$timestamp] [${BLUE}$level${NC}] $message" ;;
        *)       echo "[$timestamp] [$level] $message" ;;
    esac
}

#------------------------------------------------------------------------------
# PID CHECK (Multiple instance prevention)
#------------------------------------------------------------------------------

check_pid() {
    # Skip PID check when running under systemd (systemd handles this)
    if $RUNNING_UNDER_SYSTEMD; then
        return 0
    fi

    # Use flock for atomic PID file locking
    exec 200>"$PID_FILE.lock"
    if ! flock -n 200; then
        echo -e "${RED}ERROR: Script is already running (could not acquire lock)${NC}"
        exit 1
    fi

    # Check if old process is still running
    if [ -f "$PID_FILE" ]; then
        local old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            echo -e "${RED}ERROR: Script is already running (PID: $old_pid)${NC}"
            echo "To stop it: sudo kill $old_pid"
            flock -u 200
            exit 1
        fi
    fi

    # Write our PID (lock is held, so this is safe)
    echo $$ > "$PID_FILE"
}

cleanup_pid() {
    # Skip cleanup when running under systemd
    if $RUNNING_UNDER_SYSTEMD; then
        return 0
    fi
    rm -f "$PID_FILE" "$PID_FILE.lock"
    # Lock is automatically released when fd 200 closes (script exit)
}

#------------------------------------------------------------------------------
# LOG SIZE CHECK
#------------------------------------------------------------------------------

check_log_size() {
    if [ -f "$LOG_FILE" ]; then
        local size_kb=$(du -k "$LOG_FILE" 2>/dev/null | cut -f1)
        local size_mb=$((size_kb / 1024))
        
        if [ "$size_mb" -ge "$MAX_LOG_SIZE_MB" ]; then
            log_event "WARN" "Log file is ${size_mb}MB - rotation recommended"
            mv "$LOG_FILE" "${LOG_FILE}.old"
            log_event "INFO" "New log file created"
        fi
    fi
}

#------------------------------------------------------------------------------
# GRACEFUL SHUTDOWN
#------------------------------------------------------------------------------

shutdown_handler() {
    echo ""
    log_event "INFO" "========== Monitoring stopped =========="
    print_statistics
    cleanup_status_json
    cleanup_pid
    exit 0
}

trap shutdown_handler SIGINT SIGTERM

#------------------------------------------------------------------------------
# STATISTICS
#------------------------------------------------------------------------------

print_statistics() {
    local end_time=$(date '+%Y-%m-%d %H:%M:%S')
    local runtime=""
    
    if [ -n "$STAT_START_TIME" ]; then
        local start_sec=$(date -d "$STAT_START_TIME" +%s 2>/dev/null || echo 0)
        local end_sec=$(date +%s)
        local diff=$((end_sec - start_sec))
        local hours=$((diff / 3600))
        local mins=$(( (diff % 3600) / 60 ))
        runtime="${hours}h ${mins}m"
    fi
    
    echo ""
    echo "============================================================"
    echo "                    SESSION STATISTICS                      "
    echo "============================================================"
    echo "  Start time          : $STAT_START_TIME"
    echo "  End time            : $end_time"
    echo "  Duration            : $runtime"
    echo "------------------------------------------------------------"
    echo "  Cable connected     : $STAT_CABLE_CONNECT times"
    echo "  Cable disconnected  : $STAT_CABLE_DISCONNECT times"
    echo "  Screen turned on    : $STAT_SCREEN_ON times"
    echo "  Screen turned off   : $STAT_SCREEN_OFF times"
    echo "------------------------------------------------------------"
    echo "  Touch connected     : $STAT_TOUCH_CONNECT times"
    echo "  Touch disconnected  : $STAT_TOUCH_DISCONNECT times"
    echo "  Touch errors        : $STAT_TOUCH_ERROR times"
    echo "============================================================"
    echo ""
    
    # Write to log file (ignore errors to prevent script crash)
    {
        echo "--- Session Statistics ---"
        echo "Duration: $STAT_START_TIME - $end_time ($runtime)"
        echo "Cable: +$STAT_CABLE_CONNECT / -$STAT_CABLE_DISCONNECT"
        echo "Screen: +$STAT_SCREEN_ON / -$STAT_SCREEN_OFF"
        echo "Touch: +$STAT_TOUCH_CONNECT / -$STAT_TOUCH_DISCONNECT / err:$STAT_TOUCH_ERROR"
        echo "--------------------------"
    } >> "$LOG_FILE" 2>/dev/null || true
}

#------------------------------------------------------------------------------
# CONNECTION CHECK (xrandr)
#------------------------------------------------------------------------------

check_connection() {
    local output=$(xrandr 2>/dev/null | grep "^$DISPLAY_OUTPUT")
    
    if echo "$output" | grep -q " connected"; then
        echo "connected"
    else
        echo "disconnected"
    fi
}

#------------------------------------------------------------------------------
# PHYSICAL SIZE CHECK
#------------------------------------------------------------------------------

get_physical_size() {
    local size=$(xrandr 2>/dev/null | grep "^$DISPLAY_OUTPUT" | grep -oP '\d+mm x \d+mm')
    
    if [ -n "$size" ] && ! echo "$size" | grep -q "0mm x 0mm"; then
        echo "$size"
    else
        echo "-"
    fi
}

#------------------------------------------------------------------------------
# RESOLUTION CHECK
#------------------------------------------------------------------------------

get_resolution() {
    local mode=$(xrandr 2>/dev/null | grep "^$DISPLAY_OUTPUT" -A1 | grep '\*' | awk '{print $1}')
    echo "${mode:--}"
}

#------------------------------------------------------------------------------
# DDC/CI CHECK (Screen on/off)
#------------------------------------------------------------------------------

check_ddc() {
    if ! $DDC_AVAILABLE; then
        echo "n/a"
        return
    fi
    
    local result=$(timeout 3 ddcutil detect 2>/dev/null)
    
    if echo "$result" | grep -q "^Display"; then
        echo "on"
    else
        echo "off"
    fi
}

#------------------------------------------------------------------------------
# TOUCHSCREEN CHECK (USB + Input)
#------------------------------------------------------------------------------

check_touchscreen() {
    local usb_present=false
    local input_present=false
    
    # Check USB device
    if lsusb 2>/dev/null | grep -q "$TOUCH_USB_ID"; then
        usb_present=true
    fi
    
    # Check input device
    if xinput list 2>/dev/null | grep -qi "$TOUCH_INPUT_NAME"; then
        input_present=true
    fi
    
    # Determine status
    if $usb_present && $input_present; then
        echo "connected"
    elif $usb_present && ! $input_present; then
        echo "error"
    else
        echo "disconnected"
    fi
}

#------------------------------------------------------------------------------
# STATUS REPORT
#------------------------------------------------------------------------------

print_status_report() {
    local conn="$1"
    local res="$2"
    local size="$3"
    local ddc="$4"
    local touch="$5"
    
    local conn_display=$([ "$conn" = "connected" ] && echo "Connected" || echo "Disconnected")
    local ddc_display
    case "$ddc" in
        "on")  ddc_display="On" ;;
        "off") ddc_display="Off" ;;
        *)     ddc_display="Unknown" ;;
    esac
    local touch_display
    case "$touch" in
        "connected")    touch_display="Connected" ;;
        "error")        touch_display="Error (USB ok, input fail)" ;;
        "disconnected") touch_display="Disconnected" ;;
        *)              touch_display="Unknown" ;;
    esac
    
    echo ""
    echo "+--------------------------------------------------------------+"
    echo "|                   DISPLAY STATUS REPORT v4                   |"
    echo "+--------------------------------------------------------------+"
    printf "| %-20s : %-37s |\n" "Display Output" "$DISPLAY_OUTPUT"
    printf "| %-20s : %-37s |\n" "Cable Status" "$conn_display"
    printf "| %-20s : %-37s |\n" "Resolution" "$res"
    printf "| %-20s : %-37s |\n" "Physical Size" "$size"
    printf "| %-20s : %-37s |\n" "Screen Power" "$ddc_display"
    echo "+--------------------------------------------------------------+"
    printf "| %-20s : %-37s |\n" "Touchscreen USB" "$TOUCH_USB_ID"
    printf "| %-20s : %-37s |\n" "Touchscreen Status" "$touch_display"
    echo "+--------------------------------------------------------------+"
    printf "| %-20s : %-37s |\n" "Log File" "$LOG_FILE"
    echo "+--------------------------------------------------------------+"
    echo ""
}

#------------------------------------------------------------------------------
# MONITOR LOOP
#------------------------------------------------------------------------------

monitor_loop() {
    local curr_conn=$(check_connection)
    local curr_touch=$(check_touchscreen)
    
    # Cable connection status changed?
    if [ "$curr_conn" != "$PREV_CONNECTION" ]; then
        if [ "$curr_conn" = "connected" ]; then
            local size=$(get_physical_size)
            local res=$(get_resolution)
            log_event "INFO" "CABLE CONNECTED - Connection established (Size: $size, Resolution: $res)"
            ((STAT_CABLE_CONNECT++))
            
            # Cable just connected, check DDC immediately
            DDC_CHECK_COUNTER=$((DDC_CHECK_INTERVAL / CHECK_INTERVAL))
        else
            log_event "ERROR" "CABLE DISCONNECTED - Connection lost!"
            ((STAT_CABLE_DISCONNECT++))
            
            # Cable disconnected, reset DDC status (prevents unnecessary log)
            PREV_DDC_STATUS="off"
        fi
        PREV_CONNECTION="$curr_conn"
    fi
    
    # DDC check (only if cable is connected and enough time has passed)
    if [ "$curr_conn" = "connected" ] && $DDC_AVAILABLE; then
        ((DDC_CHECK_COUNTER++))
        
        local ddc_interval_count=$((DDC_CHECK_INTERVAL / CHECK_INTERVAL))
        
        if [ "$DDC_CHECK_COUNTER" -ge "$ddc_interval_count" ]; then
            DDC_CHECK_COUNTER=0
            
            local curr_ddc=$(check_ddc)
            
            if [ "$curr_ddc" != "$PREV_DDC_STATUS" ]; then
                if [ "$curr_ddc" = "on" ]; then
                    log_event "INFO" "SCREEN ON - DDC/CI responding"
                    ((STAT_SCREEN_ON++))
                else
                    log_event "WARN" "SCREEN OFF - DDC/CI not responding"
                    ((STAT_SCREEN_OFF++))
                fi
                PREV_DDC_STATUS="$curr_ddc"
            fi
        fi
    fi
    
    # Touchscreen status changed?
    if [ "$curr_touch" != "$PREV_TOUCH_STATUS" ]; then
        case "$curr_touch" in
            "connected")
                log_event "INFO" "TOUCHSCREEN CONNECTED - USB and input device OK"
                ((STAT_TOUCH_CONNECT++))
                ;;
            "error")
                log_event "WARN" "TOUCHSCREEN ERROR - USB present but input device not found"
                ((STAT_TOUCH_ERROR++))
                ;;
            "disconnected")
                log_event "ERROR" "TOUCHSCREEN DISCONNECTED - USB device not found!"
                ((STAT_TOUCH_DISCONNECT++))
                ;;
        esac
        PREV_TOUCH_STATUS="$curr_touch"
    fi

    # Write current status to JSON file for panel integration
    local res=$(get_resolution)
    local size=$(get_physical_size)
    write_status_json "$curr_conn" "$PREV_DDC_STATUS" "$curr_touch" "$res" "$size"
}

#------------------------------------------------------------------------------
# MAIN FUNCTION
#------------------------------------------------------------------------------

main() {
    # PID check
    check_pid
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null
    
    # Log size check
    check_log_size
    
    # Start time
    STAT_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
    
    log_event "INFO" "=========================================="
    log_event "INFO" "Display Monitor v4 started"
    if $RUNNING_UNDER_SYSTEMD; then
        log_event "INFO" "Running as systemd service"
    fi
    log_event "INFO" "=========================================="
    log_event "INFO" "Monitoring display: $DISPLAY_OUTPUT"
    log_event "INFO" "Monitoring touchscreen: $TOUCH_USB_ID"
    log_event "INFO" "Cable check interval: ${CHECK_INTERVAL}s"
    log_event "INFO" "DDC check interval: ${DDC_CHECK_INTERVAL}s"
    
    # ddcutil check
    if command -v ddcutil &> /dev/null; then
        DDC_AVAILABLE=true
        log_event "INFO" "DDC/CI support: Active"
    else
        DDC_AVAILABLE=false
        log_event "WARN" "DDC/CI support: Not available (ddcutil not installed)"
        log_event "WARN" "Screen on/off detection will not work"
        log_event "WARN" "To install: sudo apt install ddcutil"
    fi
    
    # xinput check
    if ! command -v xinput &> /dev/null; then
        log_event "WARN" "xinput not found - touchscreen input detection limited"
    fi
    
    # Get initial values
    PREV_CONNECTION=$(check_connection)
    PREV_TOUCH_STATUS=$(check_touchscreen)

    if [ "$PREV_CONNECTION" = "connected" ] && $DDC_AVAILABLE; then
        # Retry DDC check until "on" or max attempts (DDC may need time after X11 start)
        PREV_DDC_STATUS="off"
        for i in {1..5}; do
            PREV_DDC_STATUS=$(check_ddc)
            if [ "$PREV_DDC_STATUS" = "on" ]; then
                break
            fi
            sleep 1
        done
    else
        PREV_DDC_STATUS="off"
    fi
    
    local curr_res=$(get_resolution)
    local curr_size=$(get_physical_size)
    
    log_event "INFO" "Initial state - Cable: $PREV_CONNECTION, DDC: $PREV_DDC_STATUS, Touch: $PREV_TOUCH_STATUS"
    
    print_status_report "$PREV_CONNECTION" "$curr_res" "$curr_size" "$PREV_DDC_STATUS" "$PREV_TOUCH_STATUS"

    # Write initial status JSON for panel integration
    write_status_json "$PREV_CONNECTION" "$PREV_DDC_STATUS" "$PREV_TOUCH_STATUS" "$curr_res" "$curr_size"

    # Reset DDC counter so first loop check happens after full interval (DDC needs time to stabilize)
    DDC_CHECK_COUNTER=0

    echo -e "${CYAN}Monitoring active... Press Ctrl+C to stop${NC}"
    echo ""
    
    # Main loop
    while true; do
        monitor_loop
        sleep "$CHECK_INTERVAL"
    done
}

#------------------------------------------------------------------------------
# ONE-TIME STATUS CHECK
#------------------------------------------------------------------------------

status_check() {
    local conn=$(check_connection)
    local res=$(get_resolution)
    local size=$(get_physical_size)
    local ddc="n/a"
    local touch=$(check_touchscreen)
    
    if command -v ddcutil &> /dev/null && [ "$conn" = "connected" ]; then
        ddc=$(check_ddc)
    fi
    
    print_status_report "$conn" "$res" "$size" "$ddc" "$touch"
    
    # Exit code: 0=all ok, 1=cable issue, 2=screen off, 3=touch issue
    if [ "$conn" != "connected" ]; then
        exit 1
    elif [ "$ddc" = "off" ]; then
        exit 2
    elif [ "$touch" != "connected" ]; then
        exit 3
    else
        exit 0
    fi
}

#------------------------------------------------------------------------------
# HELP
#------------------------------------------------------------------------------

show_help() {
    cat << EOF
${BOLD}Display Monitor Script v4 (Final + Touchscreen)${NC}

${BOLD}USAGE:${NC}
    $0 [OPTION]

${BOLD}OPTIONS:${NC}
    --status    One-time status check and exit
    --help      Show this help message
    (none)      Run in continuous monitoring mode

${BOLD}MONITORED DEVICES:${NC}
    - Display cable (via xrandr)
    - Screen power (via ddcutil)
    - Touchscreen USB (via lsusb + xinput)

${BOLD}LOG FILE:${NC}
    $LOG_FILE

${BOLD}EXIT CODES (for --status):${NC}
    0 = All OK (cable connected, screen on, touch working)
    1 = Cable disconnected
    2 = Cable connected but screen off
    3 = Touchscreen issue

${BOLD}EXAMPLES:${NC}
    sudo $0              # Continuous monitoring
    sudo $0 --status     # One-time check
    sudo $0 --status && echo "ALL OK" || echo "PROBLEM"

EOF
}

#------------------------------------------------------------------------------
# PARAMETER HANDLING
#------------------------------------------------------------------------------

case "${1:-}" in
    --status)
        status_check
        ;;
    --help|-h)
        show_help
        ;;
    "")
        main
        ;;
    *)
        echo -e "${RED}Unknown parameter: $1${NC}"
        echo "For help: $0 --help"
        exit 1
        ;;
esac