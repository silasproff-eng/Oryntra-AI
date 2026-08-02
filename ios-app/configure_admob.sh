#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 'ca-app-pub-APP~ID' 'ca-app-pub-BANNER/ID'"
  exit 1
fi

APP_ID="$1"
BANNER_ID="$2"
PLIST="ios/Runner/Info.plist"
CONFIG="lib/app_config.dart"

if [[ ! "$APP_ID" =~ ^ca-app-pub-[0-9]+~[0-9]+$ ]]; then
  echo "Invalid AdMob iOS App ID. It must contain ~."
  exit 1
fi
if [[ ! "$BANNER_ID" =~ ^ca-app-pub-[0-9]+/[0-9]+$ ]]; then
  echo "Invalid banner ad-unit ID. It must contain /."
  exit 1
fi

python3 - "$PLIST" "$CONFIG" "$APP_ID" "$BANNER_ID" <<'PY'
from pathlib import Path
import sys
plist, config, app_id, banner_id = map(str, sys.argv[1:])
p = Path(plist)
s = p.read_text()
import re
s = re.sub(r'(<key>GADApplicationIdentifier</key>\s*<string>)[^<]+(</string>)', rf'\g<1>{app_id}\2', s)
p.write_text(s)
c = Path(config)
s = c.read_text()
s = re.sub(r"defaultValue: 'ca-app-pub-[0-9]+/[0-9]+'", f"defaultValue: '{banner_id}'", s, count=1)
c.write_text(s)
PY

echo "Installed AdMob iOS App ID and banner ad-unit ID."
