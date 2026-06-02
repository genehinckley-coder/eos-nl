# ETC EOS/ION OSC Reference
*Extracted from EOS Family User Manual v3.3.5 — Pages 812–982*

---

## Table of Contents
1. [Overview](#overview)
2. [Connection & Setup](#connection--setup)
3. [Message Structure & Conventions](#message-structure--conventions)
4. [TCP Packet Framing](#tcp-packet-framing)
5. [Command Line Control (`/eos/cmd`)](#command-line-control-eoscmd)
6. [Channel Control](#channel-control)
7. [Group Control](#group-control)
8. [Cue Playback](#cue-playback)
9. [Palettes](#palettes)
10. [Submasters](#submasters)
11. [Macros](#macros)
12. [Status & State Queries](#status--state-queries)
13. [OSC Get — Synchronization Pattern](#osc-get--synchronization-pattern)
14. [OSC Get — Detailed Packet Contents](#osc-get--detailed-packet-contents)
15. [OSC Subscribe](#osc-subscribe)
16. [OSC Outputs Reference](#osc-outputs-reference)
17. [OSC Filters](#osc-filters)
18. [OSC Set (Direct Editing)](#osc-set-direct-editing)
19. [Key Names Reference](#key-names-reference)
20. [Implementation Notes for Python](#implementation-notes-for-python)

---

## Overview

EOS supports OSC 1.0 and 1.1 for both input and output. Key rules:

- **All commands TO EOS begin with `/eos/`**
- **All commands FROM EOS begin with `/eos/out/`**
- **All requests use `/eos/get/`** and EOS replies with `/eos/out/get/`
- Case insensitive — `/eos/cmd` and `/EOS/CMD` are equivalent
- Spaces and underscores are interchangeable in parameter names
- Forward slashes in parameter names must be written as backslashes (`\`)

---

## Connection & Setup

### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| **3032** | TCP | Standard EOS OSC (preferred) |
| **3037** | UDP | Third-party OSC |
| 4703–4727, 8000, 8001 | UDP | ETC-recommended range |

### Enabling OSC in EOS
Navigate to: `Setup → System → Show Control → OSC`
- Enable `{OSC RX}` (receive) and `{OSC TX}` (transmit)
- For network interface: `ECU → Settings → Network → Interface Protocols → {UDP Strings & OSC}`

### TCP Mode Options
- **OSC 1.0** (default): 4-byte big-endian packet-length header prefix
- **OSC 1.1**: SLIP encoding

Configure via: `Setup → System → Show Control → OSC → OSC TCP mode`

### Testing the Connection — Ping
```
Send:   /eos/ping
Reply:  /eos/out/ping
```
Arguments can be added to measure latency: `/eos/ping="hello"` → `/eos/out/ping="hello"`

### Logging
Enable via Diagnostics [Tab 99]:
- `{Incoming OSC}` — log all received commands
- `{Outgoing OSC}` — log all sent commands

---

## Message Structure & Conventions

### Address Pattern Syntax
```
/eos/<command>/<target>/<action>=<argument>
```

**Argument separator:** `=` character (EOS-specific; not universal)

**Multiple arguments:** comma-separated: `/eos/cmd="Chan %1 At %2", 1, 75`

### String Substitution in `/eos/cmd`
```
/eos/cmd="Chan %1 At FL", 101       → Chan 101 At FL
/eos/cmd="Chan %1 At %2#", 1, 75   → Chan 1 At 75 (terminated)
```

### Command Termination
- `#` character terminates a command line: `"Chan 1 At 75#"`
- The word `Enter` also terminates: `"Chan 1 At 75 Enter"`
- Without termination, the command sits on the command line unexecuted

### User Scoping
Prefix `/eos/user/<number>/` to target a specific user ID:
```
/eos/user/1/cmd="Chan 1 At Full#"   → targets User 1
/eos/user/0/cmd=...                 → background user
/eos/user/-1/cmd=...                → revert to current console user
```

### Button Edge Argument
Many commands accept an optional button edge float:
- `1.0` = button down (default if omitted)
- `0.0` = button up

### OSC Local (loopback)
Prefix `local:` to loop a command back into the sending device:
```
local:/eos/chan/1=50
```

### Gel Format
```
AP1150   → Apollo 1150
L2       → Lee 2
T12      → TokyoBS Poly Color 12
```

### Number Ranges in Responses
- Consecutive whole numbers → string `"1 - 5"` format
- Single whole numbers → int32
- Decimal cue numbers → string

---

## TCP Packet Framing

### OSC 1.0 (Default — Packet-Length Headers)
EOS uses a **4-byte big-endian integer length prefix** before each packet. This is the default mode.

```python
import struct
from pythonosc import osc_message_builder

def build_osc_packet(address: str, *args) -> bytes:
    builder = osc_message_builder.OscMessageBuilder(address=address)
    for arg in args:
        if isinstance(arg, str):
            builder.add_arg(arg)
        elif isinstance(arg, float):
            builder.add_arg(arg)
        elif isinstance(arg, int):
            builder.add_arg(arg)
    msg = builder.build()
    dgram = msg.dgram
    # Prepend 4-byte big-endian length
    return struct.pack('>I', len(dgram)) + dgram

def send_osc(sock, address: str, *args):
    packet = build_osc_packet(address, *args)
    sock.sendall(packet)
```

### OSC 1.1 (SLIP Encoding)
If configured for OSC 1.1, packets use SLIP framing (RFC 1055):
- `0xC0` = END byte (packet delimiter)
- `0xDB 0xDC` = escaped END within packet
- `0xDB 0xDD` = escaped ESC within packet

---

## Command Line Control (`/eos/cmd`)

The primary way to control EOS. Sends raw EOS command-line syntax.

| Pattern | Arguments | Notes |
|---------|-----------|-------|
| `/eos/cmd` | String: command text | Unterminated — sits on cmd line |
| `/eos/cmd="Chan 1 At 75#"` | — | Terminated with `#` |
| `/eos/cmd="Chan 1 At 75 Enter"` | — | Terminated with `Enter` |
| `/eos/cmd/<text>/<text>/...` | in-line args | Slash-separated inline format |
| `/eos/newcmd` | String: command text | Clears command line first, then sends |
| `/eos/event` | String: command text | Same as cmd but treated as console event |

### Common Command Syntax via `/eos/cmd`

```
# Intensity
Chan 1 At 75 Enter                   → Channel 1 to 75%
Chan 1 At Full Enter                  → Channel 1 to 100%
Chan 1 At Out Enter                   → Channel 1 to 0%
Chan 1 Thru 5 At 50 Enter             → Channels 1–5 to 50%
Group 1 At Full Enter                 → Group 1 to full
Chan 1 Thru 999 At 0 Enter            → All channels to 0 (blackout)

# Selection
Chan 1 Enter                          → Select channel 1
Chan 1 Thru 10 Enter                  → Select channels 1–10
Group 2 Enter                         → Select group 2

# Cue Playback
Go_To_Cue 1 / 5 Enter                → Go to cue 5 in list 1
Go_To_Cue 1 / 5 Time 3 Enter         → Go to cue 5 with 3 sec fade
Go Enter                             → Advance (Go button)
Stop Enter                           → Stop/Back

# Palettes
Color_Palette 2 Enter                 → Apply color palette 2
Focus_Palette 1 Enter                 → Apply focus palette 1
Intensity_Palette 1 Enter             → Apply intensity palette 1
Beam_Palette 3 Enter                  → Apply beam palette 3

# Effects
Effect 1 Enter                        → Run effect 1
Effect 1 Stop Enter                   → Stop effect 1

# Cue Recording (SAFE MODE: BLOCK THESE)
Record Cue 1 / 10 Enter               → Record current look as cue 10
Label Cue 1 / 10 "Intro" Enter        → Label cue 10
Delete Cue 1 / 10 Enter               → Delete cue 10
```

### Command Line Output
```
/eos/out/user/<number>/cmd    → String: current command line text for user
/eos/out/cmd                  → String: current command line text (all users)
```

---

## Channel Control

### Channel Selection
```
/eos/chan=<number>                         → Select channel
/eos/chan/<number>                         → Select channel (alternate)
/eos/chan/<number>=<level>                 → Select and set intensity (0–100)
```

### Setting Channel Intensity
```
/eos/chan/<number>/full                    → Set to full (100%)
/eos/chan/<number>/out                     → Set to out (0%)
/eos/chan/<number>/home                    → Set to home value
/eos/chan/<number>/min                     → Set to minimum
/eos/chan/<number>/max                     → Set to maximum
/eos/chan/<number>/level                   → Set to Level value (Setup-defined)
/eos/chan/<number>/remdim                  → RemDim (dim everything else)
/eos/chan/<number>/+%                      → Bump up by +% (Setup-defined)
/eos/chan/<number>/-%                      → Bump down by -% (Setup-defined)
/eos/chan/<number>/DMX=<0-255>             → Set by DMX value
```

### Setting Channel Parameters
```
/eos/chan/<number>/param/<param>=<level>          → Set named parameter (0–100)
/eos/chan/<number>/param/<param>/DMX=<0-255>      → Set parameter by DMX value
/eos/chan/<number>/param/pan/tilt=45              → Set pan and tilt to 45
/eos/chan/<number>/param/pan/tilt=45,90           → Set pan=45, tilt=90
```

### Channel Color
```
/eos/chan/<number>/color/hs=<hue>,<sat>           → Hue (0–360), Saturation (0–100)
/eos/chan/<number>/color/rgb=<r>,<g>,<b>          → Red/Green/Blue (0.0–1.0 each)
/eos/chan/<number>/color/xy=<x>,<y>               → CIE 1931 xyY chromaticity
/eos/chan/<number>/color/xyz=<X>,<Y>,<Z>          → CIE XYZ color space
```

### Channel XYZ Position (Augment3D)
```
/eos/chan/<number>/xyz=<x>,<y>,<z>                → Set XYZ in decimal meters
/eos/xyz=<x>,<y>,<z>                              → Set XYZ for selected channel
```

### Channel Output (EOS → App)
```
/eos/out/active/chan    → String: active selected channels and value, e.g. "1-2 [100]"
```

---

## Group Control

Groups use the same syntax as channels but replace `chan` with `group`:

```
/eos/group=<number>                        → Select group
/eos/group/<number>=<level>                → Set group to intensity (0–100)
/eos/group/<number>/full                   → Set group to full
/eos/group/<number>/out                    → Set group to out
/eos/group/<number>/DMX=<0-255>            → Set group by DMX value
/eos/group/<number>/param/<param>=<level>  → Set group parameter
```

---

## Cue Playback

### Running Cues

| Pattern | Notes |
|---------|-------|
| `/eos/cue/fire=<cue>` | Fire cue in current list |
| `/eos/cue/<cue>/fire` | Fire specific cue |
| `/eos/cue/<list>/<cue>/fire` | Fire cue in specific list |
| `/eos/cue/<list>/<cue>/<part>/fire` | Fire specific cue part |

**`/fire/` vs `/go/`:**
- `/go/` — advances sequentially, same as physical Go button
- `/fire/` — fires regardless of sequence, can target any cue

### Cue List Playback
```
/eos/cues/<list>/fire          → Go (advance) in cue list
/eos/cues/fire                 → Go in main playback cue list
/eos/cues/<list>/stop          → Stop/Back in cue list
/eos/cues/stop                 → Stop/Back in main playback
/eos/cues/<list>               → Select cue list
/eos/cues=<list>               → Select cue list (alternate)
```

### Selecting Cues
```
/eos/cue=<cue>                    → Select cue
/eos/cue/<list>=<cue>             → Select cue in specific list
/eos/cue/<list>/<cue>=<part>      → Select cue part
```

### Key-Based Playback
```
/eos/key/go_0            → Go button
/eos/key/stop_back       → Stop/Back button
/eos/key/assert          → Assert
/eos/key/go_to_cue       → Go To Cue button
/eos/key/go_to_cue_0     → Go To Cue 0 (out)
```

---

## Palettes

### Intensity Palettes
```
/eos/ip=<number>           → Select
/eos/ip/fire=<number>      → Recall/fire
/eos/ip/<number>/fire      → Fire (button edge optional)
```

### Focus Palettes
```
/eos/fp=<number>           → Select
/eos/fp/fire=<number>      → Recall/fire
/eos/fp/<number>/fire      → Fire
```

### Color Palettes
```
/eos/cp=<number>           → Select
/eos/cp/fire=<number>      → Recall/fire
/eos/cp/<number>/fire      → Fire
```

### Beam Palettes
```
/eos/bp=<number>           → Select
/eos/bp/fire=<number>      → Recall/fire
/eos/bp/<number>/fire      → Fire
```

### Color (Current Selection)
```
/eos/color/hs=<hue>,<sat>         → Hue/Saturation on current selection
/eos/color/rgb=<r>,<g>,<b>        → RGB (0.0–1.0) on current selection
/eos/color/xy=<x>,<y>             → CIE chromaticity on current selection
```

---

## Submasters

```
/eos/sub=<number>              → Select submaster
/eos/sub/<number>=<0.0-1.0>    → Set submaster level (float 0.0–1.0)
/eos/sub/<number>/full         → Set to full
/eos/sub/<number>/out          → Set to out
/eos/sub/fire=<number>         → Bump submaster on
/eos/sub/<number>/fire=1.0     → Bump on
/eos/sub/<number>/fire=0.0     → Bump off
```

---

## Macros

```
/eos/macro=<number>            → Select macro
/eos/macro/fire=<number>       → Fire macro
/eos/macro/<number>/fire       → Fire macro (button edge optional)
```

---

## Status & State Queries

### Active Cue Status (Updates ~1/sec)
```
/eos/out/active/cue/<list>/<cue>   → Float: percent complete (0.0=started, 1.0=done)
/eos/out/active/cue                → Float: percent complete
/eos/out/active/cue/text           → String: "1/1 Label 5.00 100%"

/eos/out/pending/cue/<list>/<cue>  → Pending (next) cue identifier
/eos/out/pending/cue/text          → String: "1/1.5 Label 5.00"
```

### Show Events
```
/eos/out/event/cue/<list>/<cue>/fire    → Fires when cue executes
/eos/out/event/cue/<list>/<cue>/stop    → Fires when cue stops
/eos/out/event/sub/<sub>                → Int: 0=Bump Off, 1=Bump On
/eos/out/event/macro/<macro>            → Fires when macro executes
/eos/out/event/relay/<relay>/<group>    → Int: 0=On, 1=Off
/eos/out/event/state                    → Int: 0=Blind, 1=Live
/eos/out/show/name                      → String: show title
/eos/out/event/show/saved               → String: file path
/eos/out/event/show/loaded              → String: file path
```

### Active Wheel / Parameter Info
```
/eos/out/active/wheel/<number>    → 2 args: param name string + current value float
/eos/out/active/chan              → String: active channels + value
```

### Version
```
Send:   /eos/get/version
Reply:  /eos/out/get/version    → String: "3.3.5.69", String: fixture lib version, Bool: gel mode
```

---

## OSC Get — Synchronization Pattern

The recommended workflow for any integration application:

### Step 1: Get Version
```
/eos/get/version  →  /eos/out/get/version
```

### Step 2: Get Item Counts
```
/eos/get/patch/count           →  /eos/out/get/patch/count=<uint32>
/eos/get/group/count           →  /eos/out/get/group/count=<uint32>
/eos/get/cuelist/count         →  /eos/out/get/cuelist/count=<uint32>
/eos/get/cue/<list>/count      →  /eos/out/get/cue/<list>/count=<uint32>
/eos/get/ip/count              →  /eos/out/get/ip/count=<uint32>
/eos/get/fp/count              →  /eos/out/get/fp/count=<uint32>
/eos/get/cp/count              →  /eos/out/get/cp/count=<uint32>
/eos/get/bp/count              →  /eos/out/get/bp/count=<uint32>
/eos/get/macro/count           →  /eos/out/get/macro/count=<uint32>
/eos/get/sub/count             →  /eos/out/get/sub/count=<uint32>
/eos/get/fx/count              →  /eos/out/get/fx/count=<uint32>
/eos/get/snap/count            →  /eos/out/get/snap/count=<uint32>
/eos/get/preset/count          →  /eos/out/get/preset/count=<uint32>
/eos/get/ms/count              →  /eos/out/get/ms/count=<uint32>
/eos/get/curve/count           →  /eos/out/get/curve/count=<uint32>
/eos/get/pixmap/count          →  /eos/out/get/pixmap/count=<uint32>
```

### Step 3: Get Detailed Data (Index Loop)
Iterate from index 0 to count-1:
```
/eos/get/patch/index/<n>           →  /eos/out/get/patch/<channel>/<part>/list/...
/eos/get/group/index/<n>           →  /eos/out/get/group/<number>/list/...
/eos/get/cue/<list>/index/<n>      →  /eos/out/get/cue/<list>/<cue>/<part>/list/...
/eos/get/ip/index/<n>              →  /eos/out/get/ip/<number>/list/...
/eos/get/fp/index/<n>              →  /eos/out/get/fp/<number>/list/...
/eos/get/cp/index/<n>              →  /eos/out/get/cp/<number>/list/...
/eos/get/bp/index/<n>              →  /eos/out/get/bp/<number>/list/...
/eos/get/macro/index/<n>           →  /eos/out/get/macro/<number>/list/...
/eos/get/preset/index/<n>          →  /eos/out/get/preset/<number>/list/...
/eos/get/cuelist/index/<n>         →  /eos/out/get/cuelist/<number>/list/...
/eos/get/sub/index/<n>             →  /eos/out/get/sub/<number>/list/...
/eos/get/fx/index/<n>              →  /eos/out/get/fx/<number>/list/...
```

### Step 4: Request Specific Items (by Number or UID)
```
/eos/get/group/<number>            → Get group by number
/eos/get/group/uid/<UID>           → Get group by UID
/eos/get/cue/<list>/<cue>          → Get cue (base + all parts)
/eos/get/cue/<list>/<cue>/0        → Get base cue only
/eos/get/patch/<channel>           → Get all parts for channel
/eos/get/patch/<channel>/<part>    → Get specific channel part
```

### OSC List Convention
Large data sets are split across multiple packets. Append `/list/<index>/<count>` to the address:
```
/eos/out/get/group/2/list/0/3 = 0, "UID-STRING", "Group Label"
/eos/out/get/group/2/channels/list/0/4 = 0, "UID-STRING", 1, "11-12"
```
- `<index>` is the zero-based offset into the full list
- `<count>` is the total number of elements in the full list
- Reassemble by collecting all packets until index+count = total

---

## OSC Get — Detailed Packet Contents

### Patch (`/eos/out/get/patch/<channel>/<part>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | list index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | string | fixture manufacturer |
| 4 | string | fixture model |
| 5 | uint32 | DMX address (absolute) |
| 6 | uint32 | intensity parameter address |
| 7 | uint32 | current intensity level |
| 8 | string | gel (e.g. "L181") |
| 9–18 | string | text 1–10 |
| 19 | uint32 | part count |

### Group (`/eos/out/get/group/<number>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |

**Channel list** (`/eos/out/get/group/<number>/channels/list/<idx>/<count>`):
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | OSC Number Range | channel list (e.g. int 1, string "11-12") |

### Cue (`/eos/out/get/cue/<list>/<cue>/<part>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | uint32 | up time duration (ms) |
| 4 | uint32 | up time delay (ms) |
| 5 | uint32 | down time duration (ms) |
| 6 | uint32 | down time delay (ms) |
| 7 | uint32 | focus time duration (ms) |
| 8 | uint32 | focus time delay (ms) |
| 9 | uint32 | color time duration (ms) |
| 10 | uint32 | color time delay (ms) |
| 11 | uint32 | beam time duration (ms) |
| 12 | uint32 | beam time delay (ms) |
| 13 | bool | preheat |
| 14 | OSC number | curve |
| 15 | uint32 | rate |
| 16 | string | mark |
| 17 | string | block |
| 18 | string | assert |
| 19 | number/string | link (int=same list, string=different list) |
| 20 | uint32 | follow time (ms) |
| 21 | uint32 | hang time (ms) |
| 22 | bool | all fade |
| 23 | uint32 | loop |
| 24 | bool | solo |
| 25 | string | timecode |
| 26 | uint32 | part count (excl. base, 0=no parts) |
| 27 | string | notes |
| 28 | string | scene text |
| 29 | bool | scene end |
| 30 | int | cue part index (-1 if not part of cue) |

### Cue List (`/eos/out/get/cuelist/<number>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | string | playback mode |
| 4 | string | fader mode |
| 5 | bool | independent |
| 6 | bool | HTP |
| 7 | bool | assert |
| 8 | bool | block |
| 9 | bool | background |
| 10 | bool | solo mode |
| 11 | uint32 | timecode list |
| 12 | bool | OOS sync |

### Palette (`/eos/out/get/<ip|fp|cp|bp>/<number>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | bool | absolute |
| 4 | bool | locked |

**Channel list** (`.../channels/list/...`): index, UID, OSC Number Range

### Submaster (`/eos/out/get/sub/<number>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | string | mode |
| 4 | string | fader mode |
| 5 | bool | HTP |
| 6 | bool | exclusive |
| 7 | bool | background |
| 8 | bool | restore |
| 9 | string | priority |
| 10 | string | up time |
| 11 | string | dwell time |
| 12 | string | down time |

### Effects (`/eos/out/get/fx/<number>/list/<idx>/<count>`)
| Arg # | Type | Description |
|-------|------|-------------|
| 0 | uint32 | index |
| 1 | string | OSC UID |
| 2 | string | label |
| 3 | string | effect type |
| 4 | string | entry |
| 5 | string | exit |
| 6 | string | duration |
| 7 | uint32 | scale |

---

## OSC Subscribe

Subscribe for real-time push updates whenever show data changes:

```python
# Subscribe to all show data changes
/eos/subscribe=1        → start subscription
/eos/subscribe=0        → unsubscribe

# Subscribe to specific parameter changes
/eos/subscribe/param/red=1       → subscribe to red parameter changes
/eos/subscribe/param/red=0       → unsubscribe
```

### Change Notifications from EOS
When subscribed, EOS sends notifications when data changes:
```
/eos/out/notify/patch/list/<idx>/<count>    = <uint32: sequence_number>, ...
/eos/out/notify/group/list/<idx>/<count>    = <uint32: sequence_number>, ...
/eos/out/notify/cue/<list>/list/<idx>/<count> = <uint32: sequence_number>, ...
/eos/out/notify/cuelist/list/<idx>/<count>  = <uint32: sequence_number>, ...
/eos/out/notify/ip/list/<idx>/<count>       = <uint32: sequence_number>, ...
/eos/out/notify/fp/list/<idx>/<count>       = <uint32: sequence_number>, ...
/eos/out/notify/cp/list/<idx>/<count>       = <uint32: sequence_number>, ...
/eos/out/notify/bp/list/<idx>/<count>       = <uint32: sequence_number>, ...
/eos/out/notify/sub/list/<idx>/<count>      = <uint32: sequence_number>, ...
/eos/out/notify/macro/list/<idx>/<count>    = <uint32: sequence_number>, ...
/eos/out/notify/preset/list/<idx>/<count>   = <uint32: sequence_number>, ...
/eos/out/notify/fx/list/<idx>/<count>       = <uint32: sequence_number>, ...
/eos/out/notify/snap/list/<idx>/<count>     = <uint32: sequence_number>, ...
```

After receiving a notification, request updated data using the target number or UID:
```
/eos/get/group/<number>
/eos/get/cue/<list>/<cue>
/eos/get/patch/<channel>
```

---

## OSC Outputs Reference

Key outputs EOS sends proactively or in response to queries:

| Output Pattern | Arguments | Notes |
|----------------|-----------|-------|
| `/eos/out/active/cue` | float: percent complete | Updated ~1/sec |
| `/eos/out/active/cue/text` | string: "list/cue Label time %" | Updated ~1/sec |
| `/eos/out/pending/cue/text` | string: next cue info | |
| `/eos/out/active/chan` | string: "channels [level]" | e.g. "1-2 [100]" |
| `/eos/out/active/wheel/<n>` | string: param name, float: value | Active encoder info |
| `/eos/out/event/state` | int: 0=Blind, 1=Live | |
| `/eos/out/event/cue/<list>/<cue>/fire` | — | When cue fires |
| `/eos/out/event/cue/<list>/<cue>/stop` | — | When cue stops |
| `/eos/out/event/macro/<n>` | — | When macro fires |
| `/eos/out/show/name` | string: show title | |
| `/eos/out/event/show/saved` | string: file path | |
| `/eos/out/event/show/loaded` | string: file path | |
| `/eos/out/user` | int: user index | |
| `/eos/out/get/version` | string, string, bool | Version info |
| `/eos/out/get/patch/count` | uint32 | |
| `/eos/out/get/group/count` | uint32 | |
| `/eos/out/get/cuelist/count` | uint32 | |
| `/eos/out/get/cue/<list>/count` | uint32 | |
| `/eos/out/get/ip/count` | uint32 | |
| `/eos/out/get/fp/count` | uint32 | |
| `/eos/out/get/cp/count` | uint32 | |
| `/eos/out/get/bp/count` | uint32 | |
| `/eos/out/get/macro/count` | uint32 | |
| `/eos/out/get/sub/count` | uint32 | |
| `/eos/out/get/fx/count` | uint32 | |
| `/eos/out/get/snap/count` | uint32 | |
| `/eos/out/get/preset/count` | uint32 | |
| `/eos/out/get/ms/count` | uint32 | |
| `/eos/out/ping` | (echoed args) | Ping response |
| `/eos/out/cmd` | string | Current command line |

---

## OSC Filters

Limit which OSC messages a device receives from EOS:

```
/eos/filter/add=/eos/out/param/*    → Only receive param-related output
/eos/filter/remove=/eos/out/param/* → Remove that filter
/eos/filter/clear                   → Remove all filters (receive everything)
```

Wildcards (`*`) are supported in filter patterns.

---

## OSC Set (Direct Editing)

Used to directly edit show data labels without using the command line:

```
/eos/set/patch/<channel>/label=<string>
/eos/set/patch/<channel>/notes=<string>
/eos/set/patch/<channel>/gel=<string>
/eos/set/patch/<channel>/text1=<string>   (through text10)

/eos/set/cue/<list>/<cue>/label=<string>
/eos/set/group/<number>/label=<string>
/eos/set/macro/<number>/label=<string>
/eos/set/sub/<number>/label=<string>
/eos/set/preset/<number>/label=<string>
/eos/set/ip/<number>/label=<string>
/eos/set/fp/<number>/label=<string>
/eos/set/cp/<number>/label=<string>
/eos/set/bp/<number>/label=<string>
/eos/set/fx/<number>/label=<string>
/eos/set/snap/<number>/label=<string>
/eos/set/curve/<number>/label=<string>
/eos/set/pixmap/<number>/label=<string>
/eos/set/ms/<number>/label=<string>
/eos/set/cuelist/<number>/label=<string>
```

---

## Key Names Reference

Use with `/eos/key/<name>` (button edge argument optional):

### Playback & Navigation
```
Go_0                    → Go button
Stop_Back               → Stop/Back button (also Stop_Back_Main_CueList)
Go_To_Cue               → Go To Cue
Go_To_Cue_0             → Go To Cue 0 (out)
Assert                  → Assert
Next                    → Next
Last                    → Last
Page_Left / Page_Right  → Page navigation
Page_Up / Page_Down     → Page navigation
```

### Intensity & Selection
```
Full                    → Full
Out                     → Out (also: at out)
Rem_Dim                 → Rem Dim
Select_Active           → Select Active
Select_All              → Select All
Select_Last             → Select Last
Select_Manual           → Select Manual
```

### Targets
```
Chan        Group       Cue         Sub
Record      Preset      Effect      Macro
Beam        Focus       Color       Image
Intensity   Shutter     Label       Part
```

### Record & Edit
```
Record      Update      Record_Only     CueOnly
CueOnlyTrack    Block   Assert_cue      Delete
Undo        Label       Copy_To         Move_To
```

### Timing
```
Time        Delay       Follow      Hang
Rate        Duration    
```

### Palettes
```
Color_Palette   Focus_Palette   Intensity_Palette   Beam_Palette
```

### Modes & Display
```
Live        Blind       Setup       Spreadsheet
Cue_Sheet   Fader_Display   Magic_Sheet     Parameter_View
```

### Softkeys (1–8)
```
Softkey_1  Softkey_2  Softkey_3  Softkey_4
Softkey_5  Softkey_6  Softkey_7  Softkey_8
```

### Faders
```
Fader_1 through Fader_10    → Fader select
Stop_1 through Stop_10      → Fader stop
Bump_1 through Bump_10      → Fader bump
```

### Numeric & Entry
```
0 1 2 3 4 5 6 7 8 9   → Number keys
Enter   .   -   +   @  → Entry keys
Thru    /   Escape      
```

---

## Implementation Notes for Python

### Recommended TCP Client Pattern

```python
import socket
import struct
import threading
from pythonosc import osc_message_builder
from pythonosc.osc_message import OscMessage

EOS_HOST = "127.0.0.1"
EOS_PORT = 3032  # TCP standard port

class EosOscClient:
    def __init__(self, host=EOS_HOST, port=EOS_PORT):
        self.host = host
        self.port = port
        self.sock = None
        self._recv_buffer = b""
        
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        
    def send(self, address: str, *args):
        """Build OSC 1.0 packet with 4-byte length prefix and send."""
        builder = osc_message_builder.OscMessageBuilder(address=address)
        for arg in args:
            builder.add_arg(arg)
        msg = builder.build()
        dgram = msg.dgram
        packet = struct.pack('>I', len(dgram)) + dgram
        self.sock.sendall(packet)
        
    def send_cmd(self, command: str):
        """Send an EOS command string (terminated)."""
        if not command.endswith('#') and not command.endswith('Enter'):
            command += '#'
        self.send('/eos/cmd', command)
        
    def receive_packets(self):
        """Read OSC 1.0 length-prefixed packets from TCP stream."""
        while True:
            # Read 4-byte length header
            header = self._recv_exactly(4)
            if not header:
                break
            length = struct.unpack('>I', header)[0]
            # Read packet body
            body = self._recv_exactly(length)
            if not body:
                break
            try:
                msg = OscMessage(body)
                self._handle_message(msg)
            except Exception as e:
                print(f"Parse error: {e}")
                
    def _recv_exactly(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                return b""
            data += chunk
        return data
        
    def _handle_message(self, msg: OscMessage):
        # Override in subclass
        print(f"Received: {msg.address} {msg.params}")
```

### Show Context Initialization Sequence

```python
async def initialize_show_context(client: EosOscClient) -> dict:
    context = {}
    
    # 1. Get version
    client.send('/eos/get/version')
    
    # 2. Get counts
    client.send('/eos/get/patch/count')
    client.send('/eos/get/group/count')
    client.send('/eos/get/cuelist/count')
    client.send('/eos/get/cue/1/count')   # Cue list 1
    client.send('/eos/get/ip/count')
    client.send('/eos/get/fp/count')
    client.send('/eos/get/cp/count')
    client.send('/eos/get/bp/count')
    
    # 3. Subscribe for live updates
    client.send('/eos/subscribe', 1)
    
    # 4. Iterate indices for each type (after receiving counts)
    # ... iterate /eos/get/patch/index/<n> for n in range(patch_count)
    # ... etc.
    
    return context
```

### Rate Limiting
EOS rejects commands if flooded. Enforce minimum 50ms between commands:

```python
import asyncio
import time

class RateLimitedEosClient:
    def __init__(self, min_interval_ms=50):
        self.min_interval = min_interval_ms / 1000.0
        self._last_sent = 0.0
        self._queue = asyncio.Queue()
        
    async def send_queued(self, address, *args):
        await self._queue.put((address, args))
        
    async def _process_queue(self):
        while True:
            address, args = await self._queue.get()
            now = time.monotonic()
            elapsed = now - self._last_sent
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.send(address, *args)
            self._last_sent = time.monotonic()
```

### Parsing OSC Get Responses

```python
def parse_group_response(msg_address: str, msg_params: list) -> dict:
    """Parse /eos/out/get/group/<number>/list/<idx>/<count>"""
    parts = msg_address.split('/')
    group_number = int(parts[4])  # index 4 in /eos/out/get/group/<n>/list/...
    return {
        "number": group_number,
        "index": msg_params[0],     # uint32
        "uid": msg_params[1],       # string
        "label": msg_params[2],     # string
    }

def parse_patch_response(msg_address: str, msg_params: list) -> dict:
    """Parse /eos/out/get/patch/<channel>/<part>/list/<idx>/<count>"""
    parts = msg_address.split('/')
    return {
        "channel": int(parts[4]),
        "part": int(parts[5]),
        "uid": msg_params[1],
        "label": msg_params[2],
        "manufacturer": msg_params[3],
        "fixture_type": msg_params[4],
        "address": msg_params[5],
        "intensity_address": msg_params[6],
        "current_level": msg_params[7],
        "gel": msg_params[8],
        "text": [msg_params[i] for i in range(9, 19)],
        "part_count": msg_params[19],
    }
```

### Important Behavioral Notes

1. **Active cue output updates ~once per second** — do not use for sub-second timing
2. **Fader level feedback delayed 3 seconds** after OSC fader move
3. **OSC Cue List Banks must be created** before cue list paging works
4. **OSC Direct Selects must be created** before button events work
5. **Multi-console sessions**: all OSC traffic must go through the Host device
6. **UIDs persist across save/load** — safe to use for long-term identification
7. **OSC Reset** (`/eos/reset`) clears all persistent OSC state (user ID, wheel modes, etc.)

---

*Source: ETC EOS Family User Manual, Rev A, v3.3.5 — Pages 812–982 (OSC section)*
