#!/bin/bash
xdotool key F11 2>/dev/null &
sleep 0.5
gst-launch-1.0 -v \
    udpsrc port=5001 caps="application/x-rtp,media=video,encoding-name=H264,payload=96" ! \
    rtph264depay ! \
    avdec_h264 ! \
    autovideosink
