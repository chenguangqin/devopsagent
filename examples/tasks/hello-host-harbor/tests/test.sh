#!/bin/bash
set -euo pipefail

reward=0
if [ -f answer.txt ] && grep -qx "HOST_OK" answer.txt; then
  reward=1
fi

mkdir -p ../logs/verifier
echo "$reward" > ../logs/verifier/reward.txt
