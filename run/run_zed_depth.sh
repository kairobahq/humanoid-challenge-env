#!/usr/bin/env bash
# 실기 같은 머리 depth 로 과제 시연을 튼다 (docs/zed_depth.md). 화면 없이 돌고, 결과는 workspace/zed_depth/ 에 남는다.
#
#   ./run/run_zed_depth.sh b 0                 과제 B 시연 0 번 (0~6)
#   ./run/run_zed_depth.sh a                   과제 A 기본 판 (--seed 로 다른 판)
#   ./run/run_zed_depth.sh c 0 --zed-every 2   과제 C 0 번, 기록 2 프레임마다. 뒤의 인자는 재생기로 넘어간다
#
# 처음 한 번은 ZED 이미지를 받아 빌드하고(약 20 GB) NEURAL 모델을 이 GPU 에 맞추느라 몇 분 더 걸린다.
set -euo pipefail
TASK="${1:?과제를 준다: a, b, c}"
SEED="${2:-}"
shift $(( $# >= 2 ? 2 : $# ))
case "$TASK" in a|b|c) ;; *) echo "과제는 a, b, c 중 하나다 (받은 값 '$TASK')" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$HERE/../docker"

docker compose -f "$DOCKER_DIR/docker-compose.yaml" -f "$DOCKER_DIR/zed.yaml" up -d
echo "ZED depth 서버가 뜨기를 기다린다 (처음에는 NEURAL 모델 최적화로 몇 분) ..."
for _ in $(seq 1 240); do
  docker logs zed_depth 2>&1 | grep "기다립니다" >/dev/null && break
  if [ "$(docker inspect -f '{{.State.Running}}' zed_depth 2>/dev/null)" != "true" ]; then
    echo "zed_depth 컨테이너가 멈췄다 -- docker logs zed_depth 를 본다" >&2; exit 1
  fi
  sleep 5
done
docker logs zed_depth 2>&1 | grep "기다립니다" >/dev/null || { echo "20 분 안에 뜨지 않았다 -- docker logs zed_depth" >&2; exit 1; }

ARGS=(--headless --zed-depth)
# 과제 A · B 는 기록을 써 넣는 재생이라 사이를 채워 그릴 까닭이 없다. 과제 C 는 물리로 트므로 --substeps 를 건드리지 않는다.
[ "$TASK" != c ] && ARGS+=(--substeps 1 --hz 0)
[ -n "$SEED" ] && ARGS+=(--seed "$SEED")
exec docker exec challenge_env bash -lc \
  "cd /workspace/cyclo_lab && \${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
   /workspace/challenge_scripts/task_${TASK}_replay.py ${ARGS[*]} $*"
