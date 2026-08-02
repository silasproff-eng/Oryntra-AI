#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter is required. Install Flutter, then run this script again." >&2
  exit 1
fi

flutter pub get

if ! ruby -e "require 'xcodeproj'" >/dev/null 2>&1; then
  if command -v pod >/dev/null 2>&1; then
    echo "The xcodeproj Ruby library is missing. CocoaPods normally installs it. Reinstall CocoaPods, then rerun." >&2
  else
    echo "CocoaPods is required. Install it, then rerun." >&2
  fi
  exit 1
fi

ruby configure_widget_target.rb
cd ios
pod install --repo-update
cd ..

echo "Prepared ios/Runner.xcworkspace with the Oryntra widget target."
