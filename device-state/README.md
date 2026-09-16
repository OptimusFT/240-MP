# Device-state snapshot

This directory contains the non-secret, reproducible parts of the Raspberry
Pi configuration used with 240-MP.

Included:

- `config.json`: sanitized 240-MP preferences. Plex account, server and
  library identifiers are deliberately omitted.
- `mpv/mpv.conf`: stereo downmix, normalization and guarded volume boost.
- `retroarch/240mp-kms.cfg`: RetroArch KMS/DRM configuration.
- `retroarch/autoconfig/udev/`: controller profile used for a generic
  Xbox-compatible controller.
- `retroarch/config/PCSX-ReARMed/`: non-secret core options.
- `user_scripts/launch-retroarch.*`: generic 240-MP takeover launcher.
- `local-bin/240mp-add-psx-game`: generic helper that installs a local game
  archive and creates its launcher on the device.

Never commit Plex authentication files, private keys, ROMs, BIOS images,
save files, state files, playlists, histories, logs or device caches. The
repository ignore rules cover the corresponding snapshot locations.

The snapshot uses `$HOME`, XDG paths and `~` instead of a real user name or
home directory. It does not contain LAN/WAN addresses, host names or Wi-Fi
credentials.
