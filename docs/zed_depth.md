# 실기 같은 머리 depth (`--zed-depth`)

이 문서에서 두 낱말을 아래 뜻으로만 씁니다.

- ZED depth: ZED SDK 가 왼쪽 그림과 오른쪽 그림으로 계산한 depth.
- 정답 depth: 시뮬레이션 렌더러가 준 depth.

실기 로봇의 `head_l_depth` 는 ZED depth 입니다. 머리의 ZED Mini 가 왼쪽 그림과 오른쪽 그림을 찍고, ZED SDK 가 NEURAL 모드로
depth 를 계산합니다. 시뮬레이션의 depth 는 정답 depth 라서 오차가 없습니다.

실기 카메라 공지(2026-10-05)는 ZED depth 의 오차를 셋으로 적었습니다.

- 무늬가 있는 물체는 카메라에서 1–2 cm(1–2 %) 더 멀게 나옵니다.
- 무늬가 없는 넓은 면(흰 판, 파란 바구니 바닥)은 먼 쪽이 실제보다 위로 휘어 나옵니다.
- 물체 가장자리에서는 depth 가 1–2 cm 폭으로 주변 값과 섞입니다.

재생기(`task_a_replay.py`, `task_b_replay.py`, `task_c_replay.py`)에 `--zed-depth` 를 주면, 재생기가 같은 계산을
시뮬레이션에서 합니다. 재생기는 프레임마다 ZED depth 와 정답 depth 를 함께 저장합니다. 두 depth 를 견주면 실기에서 생길
오차를 미리 볼 수 있습니다.

이 기능은 평가에 쓰지 않습니다. `--zed-depth` 가 없으면 재생기는 이전과 똑같이 돕니다.

## 시뮬레이션에 넣는 것

| 실기 | 시뮬레이션 |
|---|---|
| ZED SDK 의 계산 | 머리에 카메라 두 대를 63 mm 간격으로 답니다. 두 그림을 실제 ZED SDK 5.5 의 NEURAL 모드에 넣습니다. |
| 카메라 값 | 정류된 그림(렌즈 왜곡을 편 그림)의 K 는 fx = fy = 363.97, 중심 (336.5, 181.0) 입니다. 실기의 중심은 (336.63, 180.86) 입니다. |
| 렌즈와 센서 | 프레임마다 렌즈 흐림(σ 0.6 px), 가장자리 어두워짐(모서리 20 %), 센서 잡음을 넣습니다. 센서 잡음은 밝을수록 커집니다. 중간 밝기에서 σ 는 약 3 입니다. |
| 조명 | 재생을 시작할 때 매장 조명의 세기(1.5–3.0 배)와 색온도(3500–6500 K)를 무작위로 정합니다. |
| calibration 오차 | ZED SDK 에 카메라 사이 거리를 실제보다 1.5 % 크게 알려 줍니다. 그래서 ZED depth 는 약 1.5 % 멀게 나옵니다. |

## 준비

ZED SDK 는 `challenge_env` 가 아닌 다른 컨테이너 `zed_depth` 에서 돕니다. 이 컨테이너에는 다음이 필요합니다.

- NVIDIA 드라이버 570 이상. ZED SDK 이미지가 CUDA 12.8 을 씁니다.
- GPU 메모리 약 2.4 GB.

아래 명령으로 컨테이너를 띄웁니다.

```bash
cd docker
docker compose -f docker-compose.yaml -f zed.yaml up -d
docker logs -f zed_depth
```

로그에 "127.0.0.1:7300 에서 기다립니다" 가 나오면 준비가 끝났습니다.

처음 한 번은 시간이 더 걸립니다. Docker 가 ZED SDK 이미지를 받아 새 이미지(약 20 GB)를 만듭니다. 그다음 ZED SDK 가 NEURAL
모델을 그 GPU 에 맞춥니다. 이 일은 몇 분 걸립니다. 맞춘 결과는 `zed-resources` 볼륨에 남으므로, 두 번째부터는 컨테이너가 바로
뜹니다.

## 실행

```bash
./run/run_zed_depth.sh b 0          # 과제 B 시연 0번 (0~6)
./run/run_zed_depth.sh a            # 과제 A 기본 시연
./run/run_zed_depth.sh c 0          # 과제 C 시연 0번
```

`run_zed_depth.sh` 는 아래 순서로 일합니다.

1. 두 컨테이너를 띄웁니다.
2. depth 서버가 준비될 때까지 기다립니다.
3. 화면 없이 재생기를 `--zed-depth` 로 돌립니다.

컨테이너 안에서 재생기를 직접 돌릴 수도 있습니다.

```bash
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u /workspace/challenge_scripts/task_b_replay.py \
    --seed 0 --headless --substeps 1 --hz 0 --zed-depth
```

과제 A 와 B 에서는 `--substeps 1 --hz 0` 을 줍니다. 두 재생기는 기록을 프레임마다 그대로 옮기므로, 프레임 사이를 채울 필요가
없습니다. 과제 C 에서는 `--substeps` 를 바꾸지 않습니다. 과제 C 재생기는 기록을 물리로 다시 계산합니다.

depth 계산은 프레임마다 약 0.4 초 걸립니다. 과제 B 시연 하나는 8–19 분 걸립니다.

## 결과 파일

재생기는 결과를 `workspace/zed_depth/<과제_시연>/` 에 저장합니다.

| 파일 | 내용 |
|---|---|
| `head_l/<프레임>.jpg` | ZED SDK 가 정류한 왼쪽 그림. ZED depth 의 픽셀이 이 그림의 픽셀과 맞습니다. |
| `depth_zed/<프레임>.png` | ZED depth. 16-bit PNG, 단위는 mm, 0 은 값이 없는 픽셀입니다. 실기의 `head_l_depth` 와 형식이 같습니다. |
| `depth_sim/<프레임>.png` | 같은 픽셀의 정답 depth. 형식은 `depth_zed` 와 같습니다. |
| `raw_l/<프레임>.jpg` | ZED SDK 에 보낸 왼쪽 그림. 50 프레임마다 하나를 저장합니다. |
| `compare.mp4` | 네 칸 영상: `head_l`, 정답 depth, ZED depth, 차이(ZED depth − 정답 depth, ±50 mm). 파란색은 ZED depth 가 더 가까운 곳, 빨간색은 더 먼 곳입니다. |
| `stats.csv` | 프레임마다 3 m 안 픽셀의 차이: 차이 크기의 중앙값, 90 % 값, 20 mm 넘게 다른 픽셀의 비율, ZED depth 가 없는 픽셀의 비율 |
| `summary.json` | 설정(조명, 잡음, 카메라)과 거리 구간별 차이 |

여러 시연의 결과를 표 하나로 모으려면 아래 명령을 돌립니다.

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh /workspace/challenge_scripts/zed_depth/zed_summary.py /workspace/user/zed_depth
```

## 옵션

| 옵션 | 기본값 | 하는 일 |
|---|---|---|
| `--zed-depth` | 끔 | ZED depth 와 정답 depth 를 저장합니다. |
| `--zed-server` | `127.0.0.1:7300` | depth 서버의 주소 |
| `--zed-out` | `/workspace/user/zed_depth` | 결과 폴더 |
| `--zed-every N` | 1 | N 프레임마다 ZED depth 를 계산합니다. |
| `--zed-frames N` | 0 (전부) | 앞에서 N 번만 ZED depth 를 계산합니다. |
| `--zed-no-sensor` | 끔 | 렌즈 흐림, 가장자리 어두워짐, 센서 잡음을 넣지 않습니다. |
| `--zed-no-video` | 끔 | `compare.mp4` 를 만들지 않습니다. |
| `--light-scale LO HI` | 1.5 3.0 | 조명 세기 배수의 범위. 매장 장면의 원래 조명이 1 입니다. 3 배보다 크면 흰 면이 하얗게 날아갑니다. |
| `--light-temp LO HI` | 3500 6500 | 색온도의 범위 (K) |
| `--light-seed N` | 무작위 | 조명의 씨앗. 같은 조명을 다시 쓰려면 로그에 찍힌 씨앗을 줍니다. |
| `--no-light-jitter` | 끔 | 매장 조명을 바꾸지 않습니다. |

## 한계

- 무늬가 있는 면이 1.5 % 멀게 나오는 것은 일부러 넣은 calibration 오차 때문입니다. 실기의 1–2 % 가 같은 원인인지는 모릅니다.
- 센서 잡음의 세기와 조명의 범위는 정한 값입니다. 실기에서 잰 값이 아닙니다.
- 공지의 숫자(흰 판 먼 끝 +9 cm 등)는 공지의 장면에서 잰 값입니다. 매장 장면에서는 크기가 다르게 나옵니다.
- `head_l` 은 시뮬레이션 머리 카메라(`--zed-depth` 없이 쓰는 카메라)와 화각이 조금 다릅니다. 시뮬레이션 머리 카메라는 fx 가
  367 이고, 중심이 그림의 한가운데입니다.
- 데모 평가 서버(`demo_server/`)는 `--zed-depth` 를 지원하지 않습니다.
