# Humanoid Challenge — 참가자 환경 (로컬 개발용)

본 대회는 ROBOTIS의 **AI Worker (FFW-SG2)** 휴머노이드 로봇을 제어하여 편의점 업무를 수행하는 시뮬레이션 챌린지입니다. 
이 저장소(Repository)는 참가자들이 자신의 로컬 PC에서 실제 대회와 완전히 동일한 환경(Isaac Sim 5.1 / Isaac Lab 2.3)을 구축하고, 데이터를 수집하여 로봇 제어 정책(Policy)을 개발할 수 있도록 제공됩니다.

> **🚨 공식 채점 및 평가 방식 안내**  
> **공식 채점은 본 저장소(로컬 환경)가 아닌 주최 측 평가 서버에서 진행됩니다.**  
> **Humanoid Challenge Repo의 목적:** 공식 채점 제출 기능은 포함되어 있지 않으며, 오직 참가자의 알고리즘 개발 및 사전 테스트 용도로만 제공됩니다.

> **📦 학습 데이터 공개**  
> 주최 측이 수집한 VLA 학습 데이터는 Hugging Face에서 확인하실 수 있습니다:
> **https://huggingface.co/datasets/SSU-RealityLab/2026CS-Store-Challenge**

> ⚠️ **채점 항목 및 가점 기준은 변경될 수 있습니다.**
> 본 저장소에 포함된 채점기와 데모 데이터는 **예시 파일**입니다. 변동 사항 발생 시 오픈 카카오톡 방과 대회 공식 사이트를 통해 공지하겠습니다.

## 3대 핵심 과제

| | Task | 과제 설명 | 로봇 제어 방식 |
|---|---|---|---|
| **A** | 진열대로 이동 | 출발지의 탁상에서 바구니를 집어 장애물을 회피한 후, 목적지 진열대 옆 책상으로 옮깁니다. | 주행 및 정지 |
| **B** | 상품 진열 | 상자에서 상품을 꺼내 진열대의 빈칸에 정확히 배치합니다. | 주행 및 정지 |
| **C** | 인식 및 계산 | 계산대 위의 상품을 하나씩 집어 스캐너에 바코드(QR)를 인식시킵니다. | 고정 (모바일 베이스 이동 없음) |

본 저장소에는 위 **세 가지 과제의 시뮬레이션 씬(Scene)**이 모두 포함되어 있습니다.

## 저장소 디렉토리 구조

```text
docker/       Docker 실행 설정. 환경 구성 코드(cyclo_lab)와 에셋은 배포 이미지 내에 포함되어 있습니다.
docs/         과제별 상세 가이드 (task_a.md · task_b.md · task_c.md)와 환경 에셋 구조(assets.md).
scripts/      주최 측 제공 스크립트 모음 (과제별 씬 생성기 및 데모 평가 서버).
              컨테이너의 /workspace/challenge_scripts 경로로 마운트됩니다.
  taskA/          과제 A 관련 파일 (데모 시연 기록 3개 포함, 채점기 포함)
  taskB/          과제 B 관련 파일 (데모 시연 기록 7개 포함, 채점기 포함)
  taskC/          과제 C 관련 파일 (정답 궤적 2개: 잡기 → QR 인식 → 내려놓기를 상품 3개에 연속 3번 — GT0 은 3개 모두 성공, GT1 은 1개 실패 / 품목별 시연 기록 4개: 1번만, 채점기 포함)
  demo_server/    채점 시스템과 동일한 방식으로 정책(Policy) 서버를 연동해보는 데모 평가 서버 (준비 중)
run/          실행 스크립트 모음. run_gui.sh는 GUI 모드로 컨테이너를 실행하며,
              run_task_*.sh는 해당 과제의 씬을 무작위로 생성하여 실행합니다.
workspace/    참가자 작업 공간. 컨테이너의 /workspace/user 경로로 마운트됩니다 (git 미추적).
```

`scripts/`와 `workspace/` 디렉토리는 마운트되어 있으므로, 업데이트 내역이 있을 경우 `git pull` 명령만 수행하면 컨테이너를 다시 빌드하지 않고도 바로 적용할 수 있습니다.

## 시스템 요구사항

- Ubuntu 22.04 (x86-64), NVIDIA GPU — **VRAM 8 GB 이상 (16 GB 이상 권장)**
- NVIDIA 드라이버: [Isaac Sim 5.1 요구사항 확인](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)
- Docker 및 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- GUI 렌더링용 X11 세션 (Wayland 환경의 경우 XWayland를 거쳐 동작합니다.)

## 시작하기

```bash
git clone git@github.com:kairobahq/humanoid-challenge-env.git
cd humanoid-challenge-env

# 1) Isaac Sim 사용 약관(EULA) 동의 — docker/.env 파일에서 ACCEPT_EULA=Y 로 변경하세요.
#    (NVIDIA Isaac Sim 라이선스에 본인이 동의함을 의미합니다.)
vi docker/.env

# 2) 로컬 머신에서 Docker 이미지 빌드 (최초 실행 시 20~40분 소요).
#    이 명령어 하나로 Isaac Sim 베이스 이미지 다운로드 및 환경 설치가 모두 진행됩니다.
./run/setup.sh

# 3) 컨테이너를 백그라운드로 실행하고 접속합니다 (Headless 모드).
cd docker
docker compose up -d
docker exec -it challenge_env bash
```

> `container ... is not running` 에러 발생 시 `docker logs challenge_env` 명령어로 로그를 확인하세요. 대개 1번(ACCEPT_EULA 동의) 단계를 누락한 경우 발생합니다.

### 스크립트 실행 시 3가지 주의사항

```bash
# 컨테이너 내부 터미널에서 실행 (또는 docker exec ... bash -lc '...')
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u <스크립트.py> --headless --enable_cameras
```

1. **Python은 절대 경로로 실행하세요.** `python` 명령어는 대화형 셸에서만 동작하므로, `docker exec` 환경에서 바로 호출하면 `python: command not found` 에러가 발생합니다.
2. **`-u` 옵션을 반드시 포함하세요.** Isaac Sim은 종료 시 프로세스를 강제 종료하므로 버퍼에 쌓인 출력이 손실될 수 있습니다. 터미널에 아무것도 출력되지 않는다면 대부분 이 옵션이 누락되었기 때문입니다.
3. **카메라를 사용하는 과제는 `--enable_cameras` 옵션이 필수입니다.** 누락 시 `RuntimeError: A camera was spawned without the --enable_cameras flag` 에러가 발생합니다.

*참고: 스크립트 실행 시 30~60초가 소요되며 다수의 경고(Warning) 메시지가 출력될 수 있으나, 이는 정상적인 동작 과정입니다.*

## 과제별 상세 가이드

세 과제의 환경 요소·생성 파라미터·데모 재생·채점 방식은 각각 별도 문서에 있습니다.
각 과제의 시작 씬은 컨테이너 안에서 `task_{a,b,c}_demo.py --seed 1000` 으로 띄웁니다.

- **[Task A — 진열대로 이동](docs/task_a.md)** — 탁상의 바구니를 집어 매장을 가로질러 책상으로 옮깁니다.
- **[Task B — 상품 진열](docs/task_b.md)** — 상자에서 상품을 꺼내 진열대의 빈칸에 배치합니다.
- **[Task C — 인식 및 계산](docs/task_c.md)** — 계산대의 상품을 집어 스캐너에 QR 을 인식시킵니다.

시뮬레이션 에셋 디렉토리 구조는 **[환경 에셋 구조](docs/assets.md)** 를 참고하세요.

## GUI 화면으로 시뮬레이터 실행하기

제공되는 셸 스크립트를 사용하면 호스트 PC의 X11 디스플레이 설정을 연동하여 도커 컨테이너를 구동하고 렌더링 화면을 직접 확인할 수 있습니다.

```bash
./run/run_gui.sh
```

* 해당 스크립트를 실행하면 **매장 기본 씬**(`scripts/basic_convstore.py`)이 로드됩니다. 편의점 매장 전체를 배경으로 로봇이 대기하고 있는 상태를 마우스로 조작하며 둘러볼 수 있습니다. (실제로 로봇을 제어하고 동작시키는 코드는 참가자가 직접 작성해야 하는 영역입니다.)
* **참고:** Isaac Sim 렌더링 윈도우가 초기화되어 화면에 나타나기까지 약 30~60초가 소요되며, 초기 구동 과정에서 터미널에 출력되는 다수의 경고(Warning) 로그는 정상적인 현상입니다.

### 다른 씬(Scene)을 GUI로 확인하는 방법

Isaac Sim 렌더링 창을 닫더라도 도커 컨테이너는 백그라운드 프로세스로 계속 실행 상태를 유지합니다. 특정 과제의 씬을 GUI 뷰어로 보려면 컨테이너 터미널에 접속한 뒤, 실행 명령어에서 `--headless` 옵션을 **제외하고** 스크립트를 실행하면 됩니다.

```bash
docker exec -it challenge_env bash

# 예시: 과제 B 데모 씬을 GUI 화면으로 구동
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_b_demo.py --seed 1000
```

### 🛠️ 트러블슈팅: GUI 창이 뜨지 않을 때

실행 후 1분이 지나도 시뮬레이터 렌더링 창이 나타나지 않는다면 다음 디스플레이 설정 항목들을 점검해 보세요.

1. **디스플레이 환경 변수 확인:** 컨테이너 내부 터미널에서 `echo $DISPLAY` 명령어를 입력하여 출력값이 정상적으로 할당되어 있는지 점검합니다.
2. **호스트 서버 권한 인가:** 호스트(Host) PC 터미널에서 `xhost +local:root` 명령어를 실행하여 도커 컨테이너의 X11 화면 접근 권한을 허용했는지 확인합니다.
3. **Wayland 호환성 점검:** 호스트 OS의 디스플레이 서버로 Wayland를 사용 중인 경우, XWayland 호환성 레이어가 정상적으로 동작하고 패키지가 설치되어 있는지 확인이 필요합니다.

## 정책 서버 구성 및 제출 안내
정책(Policy) 서버 구축을 위한 템플릿(WebSocket + msgpack 구조, 예시 정책 코드 포함)과 최종 제출 방식은 **대회 공식 홈페이지**를 통해 안내될 예정입니다. Docker 컨테이너가 `network_mode: host`로 구동되므로, 호스트 PC에서 실행된 정책 서버는 컨테이너 내부에서도 `127.0.0.1` 루프백 주소로 직접 접근할 수 있습니다.

## 채점을 미리 돌려 보는 스크립트 (준비 중)

위 설명된 `task_a_demo.py` 및 `task_b_demo.py` 스크립트는 단순히 초기 환경 장면만을 렌더링하며 실제 참가자의 정책 코드를 호출하지 않습니다. 주최 측 채점 서버와 동일한 방식으로 참가자의 정책 서버를 연동하여 시뮬레이션을 테스트해 볼 수 있는 통합 스크립트를 준비하고 있으며 프로세스는 다음과 같습니다.

1. 참가자의 정책 서버를 호스트 PC에서 구동합니다.
2. `scripts/` 디렉토리 내의 평가 스크립트가 컨테이너 내부에서 환경을 초기화하고, 실제 채점 서버와 동일한 프로토콜로 관측치(Observation)를 송신한 뒤 제어 동작(Action)을 수신하여 시뮬레이션을 진행합니다.
3. 시뮬레이션 종료 시 에피소드 요약 및 채점 결과를 출력합니다.

통신 프로토콜 및 세부 규격이 확정되는 대로 본 문서 및 `scripts/README.md`를 업데이트하여 공지할 예정입니다.

## 라이선스 고지

본 저장소의 핵심 코드(스크립트 및 Docker 구성 파일)는 Apache-2.0 라이선스를 따릅니다. 전문은 [`LICENSE`](LICENSE) 파일에서 확인할 수 있습니다.

배포 이미지에 포함된 각 구성요소의 라이선스 정보는 다음과 같습니다. 대회 주최 측이 임의로 수정한 외부 구성요소는 없으며(로봇 USD 모델은 원본 형태 그대로 사용), 상세 라이선스 전문은 배포 이미지 내 `/workspace/cyclo_lab` 경로의 `LICENSE`, `LICENSE-IsaacLab`, `THIRD_PARTY_LICENSES.md` 파일과 에셋 디렉토리의 `NOTICE_ASSETS.md` 파일에 명시되어 있습니다. **(Github 저장소 외부에서 이미지만 단독으로 다운로드하는 경우에도 본 저작권 표시가 적용됩니다.)**

| 구성요소 | 적용 라이선스 | 비고 |
|---|---|---|
| Isaac Sim (베이스 이미지) | [NVIDIA Isaac Sim Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/) | 재배포 금지 조항에 따라 참가자 본인이 NVIDIA 서버에서 직접 다운로드해야 합니다. (`.env` 파일 내 `ACCEPT_EULA=Y` 설정이 약관 동의로 간주됨) |
| Isaac Lab | BSD-3-Clause | 원본 소스코드 그대로 포함 |
| 대회 환경 코드 (cyclo_lab) | Apache-2.0 | ROBOTIS의 [robotis_lab](https://github.com/ROBOTIS-GIT/robotis_lab) 포크 버전을 기반으로 대회 환경 구성을 추가함. 원저작권 고지는 소스코드 내 유지 |
| ROBOTIS 로봇 모델 (FFW-SG2) | Apache-2.0 | 원본 USD 구조 그대로 사용 |
| whole_body_tracking 관련 코드 | MIT | `THIRD_PARTY_LICENSES.md` 문서에 출처 및 권리 고지 |
| 편의점 상품 및 집기 에셋 | 주최 측 제공 라이선스 | 대회 참가 및 연구 목적으로만 사용 가능 |
| 시식 코너 스툴 모델 | **CC BY 4.0** | 저작자 **Guy in a Poncho** ([Sketchfab 원본 링크](https://sketchfab.com/3d-models/cafe-table-and-stools-95c4acc3eebc46419f833061b8b222e7)). 과제 A 매장에 사용되었습니다. `NOTICE_ASSETS.md` 내 고지됨 — **이 표기를 절대 임의로 삭제하지 마십시오.** |
| 시식 코너 원형 탁상 | 주최 측 자체 제작 | 내부 CAD 파일 변환본 |

## 기술 지원 및 문의

대회 진행과 관련된 질의응답은 공식 홈페이지의 Q&A 게시판을 적극적으로 활용해 주시기 바랍니다.

