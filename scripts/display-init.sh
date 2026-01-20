#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Display Initialization
# Screen settings initialization script
# =============================================================================

# Default rotation
ROTATION="right"

# Try to get rotation value from MongoDB
if command -v mongosh &>/dev/null; then
    MONGO_ROTATION=$(mongosh --quiet --eval 'db.getSiblingDB("aco").settings.findOne({}, {display_rotation: 1})?.display_rotation' 2>/dev/null)
    if [[ -n "$MONGO_ROTATION" && "$MONGO_ROTATION" != "null" ]]; then
        ROTATION="$MONGO_ROTATION"
    fi
fi

# Disable screensaver
xset s off 2>/dev/null
xset -dpms 2>/dev/null
xset s noblank 2>/dev/null

# Check DISPLAY variable
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

# Wait until X/NVIDIA is ready (max 10 seconds)
echo "Waiting for X server to be ready..."
for i in $(seq 1 10); do
    CONNECTED_OUTPUT=$(xrandr 2>/dev/null | grep ' connected' | head -1 | cut -d' ' -f1)
    if [ -n "$CONNECTED_OUTPUT" ]; then
        break
    fi
    sleep 1
done

if [ -n "$CONNECTED_OUTPUT" ]; then
    echo "Display found: $CONNECTED_OUTPUT"
    echo "Rotation: $ROTATION"

    # Apply screen rotation (with retry)
    for attempt in 1 2 3; do
        xrandr --output "$CONNECTED_OUTPUT" --rotate "$ROTATION" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Screen rotation applied (attempt $attempt)"
            break
        fi
        sleep 1
    done
else
    echo "No connected display found (waited 10 seconds)"
fi

echo "Display initialization completed"
