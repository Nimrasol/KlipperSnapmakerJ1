#!/bin/bash
# Webcam support of the Snapmaker J1: a USB camera streams to Mainsail
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Run as root (sudo) by the KlipperScreen add-on:
#   snapmaker_j1_webcam.sh install   install ustreamer (Debian package)
#   snapmaker_j1_webcam.sh setup     set up the stream (idempotent)
#
# The stream: ustreamer on 127.0.0.1:8080, started by udev as soon as a
# camera is plugged in (/dev/video0) and stopped when it is unplugged;
# nginx serves it to Mainsail at /webcam/ (as MainsailOS does).  Only
# files of its own are written; the Mainsail site of nginx gets one
# include line.
set -e

USER_NAME="${SUDO_USER:-pi}"
UNIT=snapmaker-j1-webcam.service
UNIT_FILE=/etc/systemd/system/$UNIT
RULE_FILE=/etc/udev/rules.d/90-snapmaker-j1-webcam.rules
NGINX_DIR=/etc/nginx/snapmaker_j1
NGINX_FILE=$NGINX_DIR/webcam.conf
NGINX_SITE=/etc/nginx/sites-available/mainsail
INCLUDE="include $NGINX_DIR/*.conf;"
# 1280x720 at 15 frames per second: enough to watch a print, little
# network load; MJPEG cameras need no encoding (about 1% of one core of
# the display module), others are encoded at 640x480
STREAM="--device=/dev/video0 --host=127.0.0.1 --port=8080 --slowdown"
MJPEG="--format=MJPEG --resolution=1280x720 --desired-fps=15"
YUYV="--format=YUYV --encoder=CPU --resolution=640x480 --desired-fps=10"

# Write a file only when its content changes; returns 0 if it changed
put() {
    local file="$1" content="$2"
    if [ -f "$file" ] && [ "$(cat "$file")" = "$content" ]; then
        return 1
    fi
    mkdir -p "$(dirname "$file")"
    printf '%s\n' "$content" > "$file"
    return 0
}

install_package() {
    if command -v ustreamer >/dev/null; then
        echo "ustreamer is installed"
        return
    fi
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        --no-install-recommends ustreamer
    apt-get clean
}

setup() {
    command -v ustreamer >/dev/null || { echo "ustreamer missing"; exit 1; }
    local units=0 rules=0 web=0

    put "$UNIT_FILE" "# Webcam stream for Mainsail (KlipperSnapmakerJ1, scripts/snapmaker_j1_webcam.sh)
[Unit]
Description=Webcam stream (ustreamer) for Mainsail
BindsTo=dev-video0.device
After=dev-video0.device

[Service]
User=$USER_NAME
Group=video
ExecStart=/bin/sh -c 'ustreamer $STREAM $MJPEG || exec ustreamer $STREAM $YUYV'
Restart=on-failure
RestartSec=5" && units=1

    put "$RULE_FILE" "# Start the webcam stream when a camera is plugged in (KlipperSnapmakerJ1)
SUBSYSTEM==\"video4linux\", KERNEL==\"video0\", TAG+=\"systemd\", ENV{SYSTEMD_WANTS}+=\"$UNIT\"" \
        && rules=1

    put "$NGINX_FILE" "# Webcam stream of KlipperSnapmakerJ1 (scripts/snapmaker_j1_webcam.sh)
location /webcam/ {
    postpone_output 0;
    proxy_buffering off;
    proxy_ignore_headers X-Accel-Buffering;
    proxy_pass http://127.0.0.1:8080/;
}" && web=1

    if [ -f "$NGINX_SITE" ] && ! grep -qF "$INCLUDE" "$NGINX_SITE"; then
        cp "$NGINX_SITE" "$NGINX_SITE.snapmaker-j1.bak"
        sed -i "/^\s*index index.html;/a\\    $INCLUDE" "$NGINX_SITE"
        web=1
    fi
    if [ $web = 1 ]; then
        if nginx -t 2>/dev/null; then
            systemctl reload nginx
        elif [ -f "$NGINX_SITE.snapmaker-j1.bak" ]; then
            echo "nginx configuration invalid, Mainsail site restored"
            cp "$NGINX_SITE.snapmaker-j1.bak" "$NGINX_SITE"
            systemctl reload nginx
        fi
    fi

    [ $units = 1 ] && systemctl daemon-reload
    if [ $rules = 1 ] || [ $units = 1 ]; then
        udevadm control --reload
        udevadm trigger --subsystem-match=video4linux --action=add
    fi
    if [ $units = 1 ] && systemctl is-active --quiet "$UNIT"; then
        systemctl restart "$UNIT"
    fi
    echo "webcam set up"
}

case "$1" in
    install) install_package; setup ;;
    setup) setup ;;
    *) echo "Usage: $0 install|setup"; exit 1 ;;
esac
