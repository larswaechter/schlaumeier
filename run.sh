#!/bin/bash

bold=$(tput bold)
normal=$(tput sgr0)

echo -e "\n🖥️  Starting ADB server..."
adb start-server

if [[ $? -ne 0 ]]
then
  exit 1
fi

echo ""

wait_for_device() {
  echo "🔍 Searching for device..."
  adb devices | grep "\<device\>"

  if [[ $? -ne 0 ]]
  then
    echo -e "📵 No device found! Retrying in 5s...\n"
    sleep 5
    wait_for_device
  fi
}

wait_for_device

echo -e "\n🧙 ${bold}Running schlaumeier${normal}\n"

python3 main.py