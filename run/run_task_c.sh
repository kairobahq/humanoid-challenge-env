#!/usr/bin/env bash
# 과제 C 의 시작 장면을 GUI 로 한 번 세워 띄운다. X11 세션의 호스트에서 실행할 것.
# 창이 뜨기까지 30~60 초 걸리고 그동안 경고가 잔뜩 나온다. 정상이다.
# 다른 장면을 보려면 아래 SEED 를 바꾸거나, 컨테이너에 들어가 --seed 를 직접 준다.
# 씬 생성기(2026-09-26): SCENE_GEN=auto(기본, 시드 % 3 == 2 만 rand) | qr_right | rand
#   예) SCENE_GEN=rand bash run/run_task_c.sh
set -euo pipefail
SEED=1000
SCENE_GEN="${SCENE_GEN:-auto}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$HERE/../docker"

xhost +local:root
docker compose -f "$DOCKER_DIR/docker-compose.yaml" -f "$DOCKER_DIR/x11.yaml" up -d
echo "과제 C 씬(seed $SEED, 생성기 $SCENE_GEN)을 띄웁니다 — 창이 뜨기까지 30~60 초."
exec docker exec -it challenge_env bash -lc \
  "cd /workspace/cyclo_lab && \${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
   /workspace/challenge_scripts/task_c_demo.py --seed $SEED --scene-gen $SCENE_GEN"
