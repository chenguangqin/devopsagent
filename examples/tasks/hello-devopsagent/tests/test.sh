#!/bin/bash
set -euo pipefail

if [ -f /workspace/workdir.txt ] &&
   grep -qx "/workspace" /workspace/workdir.txt; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

