#!/bin/bash
VIDEO="$1"

trap 'echo "Stopping all streams..."; kill $(jobs -p) 2>/dev/null; exit' SIGINT SIGTERM

VIDEO_WIDTH=1280
VIDEO_HEIGHT=240

for ARG in "$@"; do
    case $ARG in
        video=*) VIDEO="${ARG#*=}" ;;
        width=*) VIDEO_WIDTH="${ARG#*=}" ;;
        height=*) VIDEO_HEIGHT="${ARG#*=}" ;;
        *) echo "Unknown argument: $ARG" ;;
    esac
done

declare -A BOX_LEFT=( [top]=0 [bottom]=0 [left]=0 [right]=426 [port]=5001 )
declare -A BOX_CENTER=( [top]=0 [bottom]=0 [left]=426 [right]=852 [port]=5001 )
declare -A BOX_RIGHT=( [top]=0 [bottom]=0 [left]=852 [right]=1280 [port]=5001 )

declare -A CLIENTS=(
    ["52:54:00:12:34:50"]="LEFT"
    ["3C:97:0E:75:8E:5F"]="CENTER"
#    ["52:54:00:12:34:51"]="CENTER"
    ["52:54:00:12:34:52"]="RIGHT"
)

get_ip() {
    local mac=$(echo "$1" | tr '[:upper:]' '[:lower:]')
    local ip=$(ip neighbor show | grep -i "$mac" | awk '{print $1}' | head -n 1)
    echo "$ip"
}

echo "--- Iniciando Video Wall Server ---"
echo "Video: $VIDEO (${VIDEO_WIDTH}x${VIDEO_HEIGHT})"

for MAC in "${!CLIENTS[@]}"; do
    POSITION=${CLIENTS[$MAC]}
    TARGET_IP=$(get_ip "$MAC")

    if [ -z "$TARGET_IP" ]; then
        echo "ALERTA: No se pudo encontrar IP para la MAC $MAC ($POSITION). ¿Está el cliente en línea?"
        continue
    fi

    VAR_NAME="BOX_$POSITION"
    declare -n BOX="$VAR_NAME"

    PORT="${BOX[port]}"
    TOP_CROP="${BOX[top]}"
    BOTTOM_CROP="${BOX[bottom]}"
    LEFT_CROP="${BOX[left]}"
    RIGHT_CROP=$((VIDEO_WIDTH - ${BOX[right]}))

    echo "Enviando stream $POSITION a $TARGET_IP:$PORT (MAC: $MAC)"
    echo "TOP_CROP: $TOP_CROP, BOTTOM_CROP=$BOTTOM_CROP, LEFT_CROP=$LEFT_CROP, RIGHT_CROP=$RIGHT_CROP"

    gst-launch-1.0 -q \
        filesrc location="$VIDEO" ! \
        decodebin ! queue ! \
        videocrop top=$TOP_CROP left=$LEFT_CROP right=$RIGHT_CROP bottom=$BOTTOM_CROP ! \
        videoconvert ! \
        openh264enc bitrate=4000 ! \
        rtph264pay config-interval=1 pt=96 ! \
        udpsink host=$TARGET_IP port=$PORT &
done

wait
