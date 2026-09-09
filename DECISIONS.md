# RaspTV 240-MP customizations — decision log

This file exists so that any LLM (or human) picking this project up later has
context without re-deriving it. Append to it, don't rewrite history — treat it
like a changelog with reasoning, not just a diff summary.

Device: RaspTV (Raspberry Pi, Debian 13 "trixie"), 240-MP v2026.09.07
(commit `02bc6315086b71d3cc3b187041cdc5b5da97fe4d`, upstream
`anthonycaccese/240-MP`). Owner: OptimusFT.

## Current status (read this first, then the dated log below for why)

As of 2026-09-09, on `OptimusFT/customizations`, built and deployed to this
device's production install (`/opt/240mp`), running now:

- **Plex reconnects itself automatically** after a network change (e.g. the
  Pi's Wi-Fi switching networks). Previously it would get permanently stuck
  on a dead connection until a manual logout/login. Fixed in code
  (`PlexBackend::verifyOrRefreshServerConnection()`), not a config hack.
- **RaspTV boots straight into a chosen Plex Live TV channel**, no menu
  shown, if you set one — Settings → Plex → "Live Channel". Currently set to
  a configured channel (CHANNEL-NAME) on this device. Set it to "None" to disable and boot
  to the normal menu instead.
- Both were tested against the real, running production service on this
  device (not just compiled and assumed to work) — see the dated entries
  below for the exact verification steps and log/screenshot evidence.

Not done yet (see "Known follow-ups" in the dated entries for details):
the auto-reconnect only covers the main Plex browsing/library path, not
every possible Plex network call in the app (e.g. mid-playback of a
different feature); and there's no per-Plex-user control over which app
modules are visible (discussed, not built — see the relevant dated entry).

## 2026-09-09 — Session 1 (Claude, Sonnet 5)

### Context / starting point
- User reported: after switching RaspTV's Wi-Fi network, Plex playback fails
  with a connection error to `PMS-LOCAL-IP` (the Plex Media Server's LAN IP),
  even though the server is also published externally as `PLEX-REMOTE-DOMAIN`
  and works fine from other remote Plex clients.
- Two pre-existing custom `user_scripts` were already present on the device
  (not created this session): `wifi-app/wifi.py` (a PyQt5 IR/joystick-driven
  Wi-Fi network picker, integrated into 240-MP's `com.240mp.scripts` module)
  and `televideo-app/` (unrelated teletext-style app). These predate this
  session (file timestamps from earlier the same day / before).

### Root cause found (confirmed by reading actual installed source, not the wiki)
`PlexBackend` ([`src/modules/plex/PlexBackend.cpp`](../src/modules/plex/PlexBackend.cpp))
only discovers/probes Plex server connections (local → remote WAN → relay,
`probeConnections`/`probeNext` around line 1162) **once**, right after the
initial PIN login (`fetchUsersAndServers`, ~line 1019). The winning URI is
cached forever as `active_server_uri` in
`~/.local/share/240-MP/plex_auth.json`. Nothing re-probes it afterwards:
- `checkAndRefreshOnStartup()` (line 397) only re-validates the JWT/device
  authorization (401 check), never re-probes connectivity.
- `select_server()` (line 1256) — the only user-facing "switch server" action
  — reads the already-cached URI, makes zero network calls.

So once the cached URI stops being reachable (network change in either
direction — moving away from the LAN, or moving back onto it after a login
done remotely), the app has no way to recover short of a full logout + PIN
re-login.

This is an **upstream 240-MP limitation**, not something specific to this
device or to the `wifi.py` script (which only changes the network connection
cleanly and has nothing to do with Plex's own connection cache).

### Fix applied today (data-only, no code change)
Manually replicated `fetchUsersAndServers` + `probeConnections`'s exact HTTP
calls/headers (see `PlexBackend::plexRequest`, line 128) against
`plex.tv/api/v2/resources`, confirmed `PLEX-REMOTE-DOMAIN` is a valid
registered "remote" connection for the server, probed it for real
reachability, and wrote the result into `plex_auth.json`
(`active_server_uri`, `servers`). Verified end-to-end with a real byte-range
request against an actual media file (`HTTP 206 Partial Content`,
`video/x-matroska`) — not just a metadata call.

**This fix is fragile**: it lives only in `plex_auth.json` on this specific
device and will be silently undone by any future full Plex logout/login on
this device (which re-runs the real discovery and may cache local-only again
if done from the local LAN). It is a workaround, not a resolution.

### Filed but not yet submitted: upstream bug report
Full text prepared (see chat) describing the above with code references,
ready to post to `github.com/anthonycaccese/240-MP/issues` once the user's
GitHub account recovers from a login lockout. Per that repo's
`CONTRIBUTING.md` "Note on AI Use" section: AI-assisted contributions are
explicitly welcomed, but PRs (not issues) require a disclosure of what was
AI-generated and what human review was done; this issue was drafted by
Claude but is meant to be posted by the human owner as their own report.

### Other findings from this session (informational, not yet acted on)
- **Per-Plex-user module visibility** (e.g. hide "Local Files"/"Scripts" for
  a given Plex profile): not natively supported. `AppCore::scan_for_modules()`
  reads a purely global `config.json` → `modules.<id>.enabled` flag; there is
  no code path connecting the Plex module's active user to that flag. A
  no-rebuild workaround is possible: a background script polling
  `plex_auth.json`'s `active_user_id` and rewriting `config.json`'s per-module
  `enabled` flags accordingly (the flag is read live on every `scan_for_modules()`
  call, not cached at startup). Not implemented — user did not request it yet,
  just asked about feasibility.
- **Manual module show/hide**: already exists natively. Every module manifest
  has an `"enabled"` toggle setting (default ON) rendered in that module's own
  Settings screen; turning it off removes the module from the main menu
  immediately (config is re-read on every menu display, no restart needed).

### In progress: default-boot into a specific Plex Live TV channel
User wants RaspTV to boot straight into a specific Live TV channel,
skipping the menu entirely (no UI shown before the stream starts).

Confirmed **not supported natively**, on two counts:
- `startup_module` (`AppCore::startupModuleEntryPoint()`, line 498) only
  opens a module's generic `Root.qml` — no way to pass it a deep state.
- The NFC "card" deep-link mechanism (`resolve_card()`,
  `src/modules/plex/PlexBackend.cpp:2342`, paired with
  `modules/plex/views/CardPlay.qml`) — the only existing "skip the menu, go
  straight to content" path in the app — explicitly only handles
  `movie`/`episode`/`clip`/`season`/`show` types; anything else (which
  includes Live TV channels) hits `"UNSUPPORTED ITEM TYPE"`. Live TV uses an
  entirely separate code path (`tune_channel()` + `LivePlayer.qml`, not
  `build_stream_url()` + `Player.qml`).

Plan (this session, in progress as of this entry): add a genuine code change
— see the branch's subsequent commits for the actual implementation and
rationale once done. High-level approach being pursued: a new app-level
config field (e.g. `app.startup_live_channel`) plus a `Main.qml` startup-routing
change so that, when set, the app skips `Root.qml` entirely on launch and
lands directly in `modules/plex/views/LivePlayer.qml` pre-tuned to that
channel. Requires a full C++ rebuild on-device (Pi has `BUILDING.md`/toolchain
present under `~/240-MP`).

### Backup / version-history setup
- Local branch `OptimusFT/customizations` created off upstream `main`
  (`02bc631`, tag `v2026.09.07`) specifically for these device-specific
  changes, so `main` stays clean for tracking upstream updates.
- A dedicated ed25519 SSH deploy key was generated on-device
  (`~/.ssh/github_deploy_key`, private key never leaves the Pi) to push this
  branch to the user's own fork (`github.com/OptimusFT/240-MP`) once the user
  adds the public key there as a write-enabled deploy key. No password or
  API token was requested from or handled by the assistant, by design.
- `device-state/` (this commit) snapshots the **non-secret** parts of the
  on-device configuration for history/diffing purposes:
  `config.json` (app/module settings) and `user_scripts/` (the wifi picker
  and televideo apps). Deliberately **excluded**: `plex_auth.json` (contains
  live auth tokens/JWTs) and `plex_key.pem` (private key) — these must never
  be committed to a repo, including a private one, since they're live
  credentials for the user's Plex account/server.

### Update: boot-into-Live-TV feature — implemented, built, deployed, verified

Implemented exactly the plan described above. Four small, surgical changes,
each reusing existing app machinery rather than inventing a new playback
path:

1. **`src/AppCore.h` / `src/AppCore.cpp`** — new `Q_INVOKABLE QString
   startupLiveChannel() const`, a near-copy of the existing
   `startupModuleEntryPoint()`. Reads `config["app"]["startup_live_channel"]`.
   `"None"`/unset = feature off.
2. **`Main.qml`** — at the existing app-startup routing point (inside
   `moduleLoader.onLoaded`), now also calls `appCore.startupLiveChannel()`
   and passes it through as `navParams.autoLiveChannel` alongside the
   existing `fromAppStartup: true`. Harmless no-op for any module other than
   Plex, which simply ignores an unrecognized navParams key.
3. **`modules/plex/views/Root.qml`** — new branch inside the existing
   `state === "authed"` case (same gating as the pre-existing
   `Libraries.qml` branch: only fires if `auto_sign_in` is ON, so it never
   bypasses a profile-choice prompt that would otherwise show): if
   `navParams.autoLiveChannel` is set, navigates straight to
   `LiveChannels.qml` with `{ autoSelectNumber: ... }` instead of
   `Libraries.qml`. Modeled directly on the pre-existing `navParams.cardRef`
   ahead-of-gate branch used for NFC card taps.
4. **`modules/plex/views/LiveChannels.qml`** — in `onLiveChannelsLoaded`,
   if `autoSelectNumber` is set and hasn't already fired this view instance
   (`autoSelectDone` guard, so returning to this list later behaves
   normally), finds the channel whose `number` matches and calls the exact
   same `navigateTo("LivePlayer.qml", { channel: ... }, ...)` that pressing
   Enter on a channel row already calls. No new tuning/session-management
   code at all — 100% reuse of the existing, already-shipped tune/play path.
   No match found: silently falls through to the normal channel list
   (no error, no loop).

**Device config change** (`~/.local/share/240-MP/config.json`, backed up
first as `config.before-live-tv-startup-<timestamp>.json`):
- `app.startup_module` = `"com.240mp.plex"` (was `"None"`) — required for
  `Main.qml` to even resolve an entry point to launch into at boot.
- `app.startup_live_channel` = the configured channel's number.
- `modules["com.240mp.plex"].auto_sign_in` = `true` (was unset/OFF) —
  required side effect: boot now always signs in as the cached profile
  without showing the profile picker. Flagged to the user as a real
  behavior change, not silently enabled.

**Build**: toolchain wasn't installed on-device (this is a release-tarball
install via `install.sh`, not a from-source build). Installed the
`BUILDING.md` Raspberry Pi prerequisite package list via apt (cmake, Qt6
dev packages, etc.), then `cmake -B build && cmake --build build -j4` from
`~/240-MP` (branch `OptimusFT/customizations`). Clean build, zero errors.

**Deployment**: discovered — before touching anything — that this device
runs the app from a separately-installed release tree (`/opt/240mp/bin/240mp`
+ `/opt/240mp/share/240mp/...`, managed by `240mp.service`/systemd, launched
through a wrapper at `/usr/local/bin/240mp`), *not* directly from
`~/240-MP`. Also found evidence another AI agent ("Codex") had already been
working on this exact device earlier today (`/var/backups/240mp-codex-*`,
`/var/tmp/240mp-codex/`, multiple timestamped backups of
`/usr/local/bin/240mp`) — did not touch or overwrite any of that, left it as
found.

Before deploying: full tarball backup of the pre-change `/opt/240mp` tree to
`/var/backups/opt-240mp-pre-livetv-<timestamp>.tar.gz` (root-owned, in
addition to Codex's own earlier backups). Then:
- Stopped `240mp.service` (user confirmed OK to interrupt the live TV output
  for testing).
- Ran the new `~/240-MP/build/240mp` manually first (`APP_ROOT=$(pwd)
  QT_QPA_PLATFORM=eglfs ...`), *before* touching the production copy, to
  validate the change with zero risk to the working install.
- Only after that manual run proved clean (see verification below) were
  `/opt/240mp/bin/240mp`, `/opt/240mp/share/240mp/Main.qml`, and the two
  changed Plex `views/*.qml` files replaced, then `240mp.service` restarted.

**Verification (no visual/screen access used at any point — this device has
no monitor attached during this session)**:
- First manual run (this LAN, no working outbound HTTPS — see the
  `PLEX-REMOTE-DOMAIN`/Fortinet finding earlier in this log): reached
  `LiveChannels.qml`'s `load_live_channels()` call with **zero QML errors**
  before failing on the network layer (`SSL handshake failed`) — proof the
  new navigation wiring itself (AppCore → Main.qml → Root.qml →
  LiveChannels.qml) is correct, independent of network conditions.
- Re-ran after reconnecting the (temporary, testing-only) Wi-Fi hotspot and
  making it the preferred route (`ip route replace default ... dev wlan0
  metric 50` — a live, non-persistent change, not written to any config):
  log line `[Plex] Live stream URL for mpv: "https://PLEX-REMOTE-DOMAIN/...
  /base/index.m3u8"` appeared unprompted, and `ps aux` showed a live `mpv`
  process actively decoding (`AV: 00:00:35/37 ... Dropped: 1`).
- Repeated the same verification against the **deployed production binary**
  under the real `240mp.service` (not just the manual dev run): journal
  showed one transient `LIVE STREAM FAILED` (stale tuner session left over
  from the killed manual test, self-recovered) immediately followed by a
  second, successful `[Plex] Live stream URL for mpv: ...`, with `mpv`
  confirmed running and pulling real HLS segments
  (`.../base/00032.ts`, `00033.ts`, ...) from `PLEX-REMOTE-DOMAIN`.

**Known follow-ups, not done in this session** (listed so a future session
doesn't need to rediscover them):
- ~~No in-app Settings UI control for `startup_live_channel` yet — it's a
  config-file-only setting for now.~~ **Resolved in the entry below** (a
  proper Settings screen picker was added the same day).
- The live route-priority override used for testing
  (`ip route ... metric 50`) is **not persistent** — it was a live kernel
  routing change only, gone on reboot / already superseded once the device
  is on its real target network. Nothing to clean up there.
- Should confirm real-world behavior once RaspTV is back on its actual home
  network (this session's verification network was a phone hotspot used
  purely because the office LAN blocks the destination).

### Update: the real Plex reconnect fix (not just today's manual workaround), a Settings UI channel picker, and a navigation bug found while testing

**1. Actual code fix for the original bug** (see the very first entry in
this log — until now that was only patched by hand-editing
`plex_auth.json`). Added `PlexBackend::verifyOrRefreshServerConnection()`
([src/modules/plex/PlexBackend.cpp](../src/modules/plex/PlexBackend.cpp),
declared in the .h next to `fetchLiveChannelList`), wired into
`checkAndRefreshOnStartup()`'s `proceed` lambda so it runs on *every*
`load_libraries()` call (not gated by `m_deviceVerified`, unlike the
401/deauth check right after it -- a network change can happen at any point
while the app keeps running, so this can't be a once-per-session check).
Behavior: a cheap reachability probe of the cached `active_server_uri`
(same any-HTTP-response-counts rule `probeNext()` already uses, 3s
timeout); only on failure does it re-fetch `/api/v2/resources`, find the
current server's `connections`, and run them through the existing
`probeConnections()` — i.e. exactly what `fetchUsersAndServers()` does at
login, just scoped to the one already-active server instead of the whole
account. On success it rewrites `active_server_uri` (and the matching
`servers[]` entry) in `plex_auth.json`.

Verified for real, automatically, with no manual step: backed up
`plex_auth.json`, set `active_server_uri` to an unreachable address
(`https://198.51.100.1:32400`), then simply opened the Plex module from the
main menu (which calls `load_libraries()`). Journal showed:
```
[PlexAuth] active_server_uri unreachable, re-discovering connections for 226bee...
[PlexAuth] Reconnected to NAS via remote after network change
[PlexAuth] load_libraries mid= …1ce7 token= opaque len=20
```
`active_server_uri` was back to `https://PLEX-REMOTE-DOMAIN` on disk, and a
screenshot (captured via `ffmpeg -f kmsgrab`, see below) confirmed the
Libraries screen loaded normally afterward.

Scope note: this covers the path that matters most (browsing/opening the
Plex module, which is what `load_libraries()` gates). It does not cover
every other `serverUrl()` call site in `PlexBackend.cpp` (e.g. a card tap
via NFC, or an in-progress live-TV session) — those still assume the cached
URI is good. Widening this to a truly universal fix is a reasonable
follow-up, not done here to keep this change small and well-tested.

**2. Settings UI for the boot-into-channel feature** (previously
config-file-only). Added a proper module setting instead of a raw config
edit:
- `modules/plex/manifest.json`: new `startup_live_channel` entry
  (`list_single`, `options_source: dynamic`, `options_slot:
  get_startup_channel_options`), right after `auto_sign_in`.
- `PlexBackend::get_startup_channel_options()` — follows the exact same
  pattern as the pre-existing `getLibraries()` (a real network-backed async
  dynamic-options slot, not a fixed local list): shares a new private
  `fetchLiveChannelList()` helper with `load_live_channels()` (refactored
  out of the old `load_live_channels()` body, zero behavior change there)
  and reshapes the result into `{id, label}` pairs for the Settings screen,
  with a leading "NONE" entry to disable the feature. `id` is the channel
  *number* (not the internal `channelId`) so it matches
  `LiveChannels.qml`'s `autoSelectNumber` comparison directly.
- Storage moved from `app.startup_live_channel` to the more natural
  `modules["com.240mp.plex"].startup_live_channel` (it's a Plex-specific
  choice, not a general app setting) — `AppCore::startupLiveChannel()`
  updated to read the new path. Device config migrated to match.

Verified with a real screenshot of the rendered setting (see below):
`Settings → Plex → "START ON LIVE CHANNEL: <number>  <channel name>"`, live-fetched label,
not a placeholder.

**3. Bug found and fixed while testing (2) with a real device screenshot**:
backing out of a live channel (Escape in `LivePlayer.qml` → back to
`LiveChannels.qml`) was silently re-triggering the boot auto-select and
re-tuning the *same* startup channel every time, because Root.qml's
navigation stack (`navStack`) restores the exact params object a view was
originally opened with — including `autoSelectNumber` — so any return trip
to `LiveChannels.qml` looked like a fresh boot to it. Net effect: once
`startup_live_channel` was set, a user could never actually browse to a
*different* channel from the list; back always snapped to the configured
one. Fixed with a new `LiveChannels.qml` → `Root.qml` signal,
`clearAutoSelect()`, emitted right before the one-time auto-navigate to
`LivePlayer.qml` fires; `Root.qml` handles it by clearing
`moduleRoot.currentParams`, so the navStack entry pushed for the return
trip no longer carries the auto-select instruction. Confirmed visually: a
transient tune failure (unrelated stale-tuner condition from repeated
testing) correctly left the plain channel list on screen instead of
looping.

**4. Screenshots without a monitor**: this device has no display attached to
verify against visually during this session, so all of the above was
confirmed with real screen captures instead of taking success on faith:
- `ffmpeg -f kmsgrab -device /dev/dri/card1 -i - -frames:v 1 -vf
  'hwdownload,format=bgr0' out.png`, run as root (kmsgrab needs
  `CAP_SYS_ADMIN` to read framebuffer handles — a normal user gets "No
  handle set on framebuffer"). VAAPI-based hwmap doesn't work on this
  Pi (mesa has no VAAPI driver for the v3d GPU); direct `hwdownload`
  without vaapi works fine.
- Since no physical remote/keyboard is attached either
  (`/proc/bus/input/devices` had nothing but a phantom mouse), navigation
  was driven by a temporary virtual input device
  (`python3-evdev`'s `UInput`, root-only) sending standard Linux keycodes
  (`KEY_UP/DOWN/ENTER/ESC`) that Qt's evdev backend picks up like any other
  keyboard. Removed after use; nothing persists from this beyond the code
  changes.
