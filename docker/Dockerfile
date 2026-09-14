# 참가자 배포 이미지 — 과제 환경만.
#
# 대회 개발 환경(cstore-challenge/docker/Dockerfile.base)에서 참가자에게 필요 없는 것을
# 덜어낸 것이다. 무엇을 왜 뺐는지 적어 둔다 — 이미지가 정본이므로 여기가 그 기록이다.
#
#   빠진 것                   왜
#   ------------------------  --------------------------------------------------------
#   cuRobo                    모션 플래너. 대회 측이 시연을 모을 때 쓴 도구이고 과제를
#                             푸는 데 필요하지 않다. CUDA 커널을 런타임에 컴파일해서
#                             이미지와 첫 실행 시간을 둘 다 크게 만든다.
#   GraspGen 파지 파일         같은 이유. 대회 측 수집 도구의 입력이다.
#   CycloneDDS / robotis_dds  실제 로봇과 통신하는 계층. 시뮬레이션만 하는 이 이미지의
#                             파이썬 코드는 dds 를 한 줄도 import 하지 않는다(확인함).
#                             빼면 cmake 컴파일 단계 하나가 통째로 사라진다.
#   LeRobot venv              데이터셋 변환용. 참가자는 자기 학습 환경을 따로 쓴다.
#   수집한 시연 데이터          환경이 아니라 대회 측의 산출물이다.
#   과제 B 밖의 에셋           매장 씬, 과제 C 상품 등. 과제가 늘면 함께 들어온다.
#
# 이 Dockerfile 은 대회측이 추려 배포하는 트리(challenge-overlay.tar.gz 를 푼 stage/)를
# 받는 것을 전제로 한다.

ARG ISAACSIM_BASE_IMAGE=nvcr.io/nvidia/isaac-sim
ARG ISAACSIM_VERSION=5.1.0
FROM ${ISAACSIM_BASE_IMAGE}:${ISAACSIM_VERSION} AS base

SHELL ["/bin/bash", "-c"]

LABEL description="Humanoid Challenge 참가자 환경 — Isaac Sim 5.1 + Isaac Lab + 과제 환경"

ARG ISAACSIM_ROOT_PATH=/isaac-sim
ARG CYCLOLAB_PATH=/workspace/cyclo_lab
ARG DOCKER_USER_HOME=/root
ENV ISAACSIM_ROOT_PATH=${ISAACSIM_ROOT_PATH}
ENV CYCLOLAB_PATH=${CYCLOLAB_PATH}
ENV DOCKER_USER_HOME=${DOCKER_USER_HOME}
ENV ISAACLAB_PATH=${CYCLOLAB_PATH}/third_party/IsaacLab

ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
# isaaclab.sh 13 행이 `set -e`, 16 행이 `tabs 4` 다. TERM 이 없으면 tabs 가 0 이 아닌 값으로
# 끝나고 스크립트가 아무 것도 찍지 못한 채 죽는다.
ENV TERM=xterm

USER root

# git 은 없으면 isaaclab.sh --install 이 실패한다(의존성 하나가 setuptools_scm 으로 버전을
# 찾는다). isaac-sim 이미지에는 git 도 컴파일러도 들어 있지 않다.
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libglib2.0-0 \
    libevdev-dev \
    ncurses-term \
    python3-dev \
    python3-pip \
    && apt -y autoremove && apt clean autoclean \
    && rm -rf /var/lib/apt/lists/*

# 대회측이 추려 놓은 트리. 무엇이 들어 있는지는 docs/assets.md 가 적는다.
COPY stage/ ${CYCLOLAB_PATH}/

# 에셋은 코드와 떨어진 /workspace/assets 에 둔다. 환경 코드(cyclo_lab)는 패키지 옆
# source/cyclo_lab/data 를 찾으므로 그 자리에 링크를 건다.
RUN mv ${CYCLOLAB_PATH}/assets /workspace/assets && \
    ln -s /workspace/assets ${CYCLOLAB_PATH}/source/cyclo_lab/data

# 과제 C 상품 8종 중 5종(chilsung_cider·lotte_sand·pringles_sourcream_small·samyang_buldak_cup·yegam_original)의
# `<이름>_phys.usd` 는 보이는 메시 `.usdc` 를 수집 저장소 자리인 `/workspace/cyclo_lab/taskC/out/qr_usd/…`
# 절대 경로로 문다(2026-09-14 실측). 그 자리가 없으면 물리 콜라이더만 남고 메시·QR 텍스처가 안 떠서
# 스캐너 카메라가 QR 을 못 읽는다. 채점기(scripts/taskC/scorer/score_from_trace.py)도 기대 바코드를
# 같은 경로의 info.json 에서 읽는다. 그 자리를 products_c 로 이어 준다.
RUN mkdir -p ${CYCLOLAB_PATH}/taskC/out && \
    ln -s /workspace/assets/products_c ${CYCLOLAB_PATH}/taskC/out/qr_usd

RUN chmod +x ${ISAACLAB_PATH}/isaaclab.sh && \
    ln -sf ${ISAACSIM_ROOT_PATH} ${ISAACLAB_PATH}/_isaac_sim

RUN ${ISAACLAB_PATH}/isaaclab.sh -p -m pip install toml

RUN --mount=type=cache,target=/var/cache/apt \
    ${ISAACLAB_PATH}/isaaclab.sh -p ${ISAACLAB_PATH}/tools/install_deps.py apt ${ISAACLAB_PATH}/source && \
    apt -y autoremove && apt clean autoclean && \
    rm -rf /var/lib/apt/lists/*

# flatdict==4.0.1 (isaaclab 의존성) 은 setup.py 가 pkg_resources 를 import 하는데 pip 의
# 격리된 빌드 환경에는 그게 없어서 휠 빌드가 깨진다. 격리 없이 미리 넣어 둔다.
RUN --mount=type=cache,target=${DOCKER_USER_HOME}/.cache/pip \
    ${ISAACLAB_PATH}/isaaclab.sh -p -m pip install --no-build-isolation flatdict==4.0.1

RUN --mount=type=cache,target=${DOCKER_USER_HOME}/.cache/pip \
    ${ISAACLAB_PATH}/isaaclab.sh --install

RUN ${ISAACLAB_PATH}/isaaclab.sh -p -m pip uninstall -y quadprog

# 정책 서버 프로토콜(WebSocket + msgpack) -- scripts/demo_server 가 쓴다.
# websockets 는 13 미만이면 sync API 의 ssl/additional_headers 인자 이름이 달라
# 템플릿(server.py)과 demo_server 가 둘 다 죽는다 (12.0 으로 실측).
RUN --mount=type=cache,target=${DOCKER_USER_HOME}/.cache/pip \
    ${ISAACLAB_PATH}/isaaclab.sh -p -m pip install "websockets>=13" msgpack msgpack-numpy

RUN --mount=type=cache,target=${DOCKER_USER_HOME}/.cache/pip \
    cd ${CYCLOLAB_PATH}/source/cyclo_lab && \
    ${ISAACLAB_PATH}/isaaclab.sh -p -m pip install -e .

# 캐시 볼륨이 붙을 자리를 미리 만들어 둔다 (docker-compose.yaml 의 isaac-cache-* 들).
RUN mkdir -p ${ISAACSIM_ROOT_PATH}/kit/cache \
             ${DOCKER_USER_HOME}/.cache/ov \
             ${DOCKER_USER_HOME}/.cache/pip \
             ${DOCKER_USER_HOME}/.cache/nvidia/GLCache \
             ${DOCKER_USER_HOME}/.nv/ComputeCache \
             ${DOCKER_USER_HOME}/.nvidia-omniverse/logs \
             ${DOCKER_USER_HOME}/.local/share/ov/data \
             /workspace/challenge_scripts \
             /workspace/user

RUN { \
      echo "export ISAACLAB_PATH=${ISAACLAB_PATH}"; \
      echo "export CYCLOLAB_PATH=${CYCLOLAB_PATH}"; \
      echo "alias isaaclab=${ISAACLAB_PATH}/isaaclab.sh"; \
      echo "alias python=${ISAACLAB_PATH}/_isaac_sim/python.sh"; \
      echo "alias python3=${ISAACLAB_PATH}/_isaac_sim/python.sh"; \
      echo "alias pip='${ISAACLAB_PATH}/_isaac_sim/python.sh -m pip'"; \
    } >> ${DOCKER_USER_HOME}/.bashrc

# 마지막에 둔다 -- 이 파일만 고쳐도 위의 무거운 단계들이 캐시에서 살아나도록.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR ${CYCLOLAB_PATH}
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
