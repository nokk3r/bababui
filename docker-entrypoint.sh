#!/bin/sh
set -e
mkdir -p /data
chown checker:checker /data
exec runuser -u checker -- "$@"
