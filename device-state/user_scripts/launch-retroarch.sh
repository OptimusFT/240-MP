#!/bin/bash
set -u

config_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/retroarch"
append_config="$config_dir/240mp-kms.cfg"
state_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/240-MP"
mkdir -p "$state_dir"
log_file="$state_dir/retroarch.log"

{
  printf '=== RetroArch launch: %s ===\n' "$(date --iso-8601=seconds)"
  printf 'Available DRM nodes:\n'
  ls -la /dev/dri
  printf 'Composite connector state:\n'
  grep -H . /sys/class/drm/card*-Composite-1/status /sys/class/drm/card*-Composite-1/enabled 2>/dev/null || true
  printf 'RetroArch output:\n'
  if [ ! -r "$append_config" ]; then
    printf 'Required append configuration is missing: %s\n' "$append_config"
    exit 2
  fi
  exec /usr/bin/retroarch --fullscreen --verbose --config "$append_config"
} >>"$log_file" 2>&1
