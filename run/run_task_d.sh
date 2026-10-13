#!/usr/bin/env bash
# 태스크 D 의 시작 장면을 GUI 로 한 번 세워 띄운다. X11 세션의 호스트에서 실행할 것.
# 씨앗을 바꾸려면: SEED=7 run/run_task_d.sh
# 배경 기물을 빼려면: EXTRA=--no-clutter run/run_task_d.sh
set -euo pipefail
SEED="${SEED:-1000}"
EXTRA="${EXTRA:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; DOCKER_DIR="$HERE/../docker"
xhost +local:root
docker compose -f "$DOCKER_DIR/docker-compose.yaml" -f "$DOCKER_DIR/x11.yaml" up -d
exec docker exec -it challenge_env bash -lc \
  "cd /workspace/cyclo_lab && \${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
   /workspace/challenge_scripts/task_d_demo.py --seed $SEED $EXTRA"
