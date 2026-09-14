#!/usr/bin/env bash
# 과제 C 시연 기록 한 판을 GUI 로 물리 재생한다. X11 세션의 호스트에서 실행할 것.
# 창이 뜨기까지 30~60 초 걸리고 그동안 경고가 잔뜩 나온다. 정상이다.
# 다른 판을 보려면 아래 SET/SEED 를 바꾸거나, 컨테이너에 들어가 --set/--seed 를 직접 준다.
#
# run_task_c.sh 는 **시작 장면**을 세우고 멈춘다. 이쪽은 그 다음 -- 상품을 집어 스캐너에
# 비추고 제자리에 놓는 한 판을 튼다. --set gt 는 상품 3개 연속(정답 궤적 2편, 220~230 초),
# --set single 은 상품 하나(학습 데이터 형식, 60~100 초)다.
set -euo pipefail
SET=gt
SEED=0

# 허깅페이스에 공개된 학습 데이터를 직접 틀려면 아래 둘을 채운다 (그때는 SET/SEED 를 안 쓴다).
# 경로는 **컨테이너 안에서 보이는** 경로여야 한다 -- docker-compose.yaml 에 마운트를 더하거나
# 데이터셋을 이 저장소 아래에 두면 된다. 편 번호는 meta/taskC_episodes.jsonl 의 episode_index.
#   https://huggingface.co/datasets/SSU-RealityLab/2026CS-Store-Challenge
LEROBOT=""
EPISODE_INDEX=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$HERE/../docker"

xhost +local:root
docker compose -f "$DOCKER_DIR/docker-compose.yaml" -f "$DOCKER_DIR/x11.yaml" up -d
if [ -n "$LEROBOT" ]; then
  ARGS="--lerobot $LEROBOT --episode-index $EPISODE_INDEX"
  echo "과제 C — 학습 데이터 $EPISODE_INDEX 번 편을 튭니다 — 창이 뜨기까지 30~60 초."
else
  ARGS="--set $SET --seed $SEED"
  echo "과제 C 시연($SET, seed $SEED)을 튭니다 — 창이 뜨기까지 30~60 초."
fi
exec docker exec -it challenge_env bash -lc \
  "cd /workspace/cyclo_lab && \${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
   /workspace/challenge_scripts/task_c_replay.py $ARGS"
