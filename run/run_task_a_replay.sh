#!/usr/bin/env bash
# 과제 A 한 판을 처음부터 끝까지 GUI 로 틀어 준다. X11 세션의 호스트에서 실행할 것.
# 창이 뜨기까지 30~60 초 걸리고 그동안 경고가 잔뜩 나온다. 정상이다.
# 다른 판을 보려면 아래 SEED 를 0 / 2 / 6 중에서 바꾸거나, 컨테이너에 들어가 --seed 를 직접 준다.
#
# run_task_a.sh 는 **시작 장면**을 세우고 멈춘다. 이쪽은 그 다음 -- 탁상에서 바구니를 집고,
# 매장을 가로질러, 목적지 책상에 내려놓는 한 판 전부를 튼다. 한 판은 135~189 초다.
#
# 들어 있는 세 판은 전부 평가표 만점(21/21)이다:
#     --seed 0   좌석  0   147 초
#     --seed 2   좌석 10   135 초
#     --seed 6   좌석  6   189 초
#
# 무엇이 들어 있는지만 보려면 (Isaac Sim 을 안 띄운다 -- 1 초):
#     docker exec -it challenge_env bash -lc \
#       '${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
#        /workspace/challenge_scripts/task_a_replay.py --list'
set -euo pipefail
SEED=6
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$HERE/../docker"

xhost +local:root
docker compose -f "$DOCKER_DIR/docker-compose.yaml" -f "$DOCKER_DIR/x11.yaml" up -d
echo "과제 A 정답 주행(seed $SEED)을 틉니다 — 창이 뜨기까지 30~60 초."
exec docker exec -it challenge_env bash -lc \
  "cd /workspace/cyclo_lab && \${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
   /workspace/challenge_scripts/task_a_replay.py --seed $SEED"
