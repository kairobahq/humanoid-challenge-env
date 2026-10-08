# 실기 같은 머리 depth — `--zed-depth`

본선 실기 로봇이 주는 `head_l_depth` 는 머리 ZED Mini 의 두 눈 그림을 **ZED SDK(NEURAL)** 가 계산한 depth 입니다.
시뮬레이션의 depth 는 렌더러가 주는 정답이라 노이즈도 왜곡도 없습니다. 그래서 실기에서는 다음이 달라집니다
(실기 카메라 공지, 2026-10-05).

- 무늬 있는 물체는 형상이 잘 잡히지만 카메라 광선 방향으로 약 1–2 cm(1–2 %) 멀게 읽힙니다.
- 무늬 없는 넓은 면(흰 판, 파란 바구니 바닥 등)은 카메라에서 먼 쪽으로 갈수록 실제보다 위로 휘어 보입니다.
- 물체 가장자리의 depth 는 1–2 cm 폭으로 주변과 섞입니다.

과제 A · B · C 의 재생기(`task_a_replay.py` · `task_b_replay.py` · `task_c_replay.py`)에 `--zed-depth` 를 주면
**같은 계산을 시뮬레이션에서** 합니다. 시연을 틀면서 프레임마다 실기와 같은 방식의 depth 와 시뮬레이션 정답 depth 를
나란히 남기므로, 정책이 depth 를 얼마나 믿어도 되는지 미리 볼 수 있습니다. 평가에는 쓰지 않습니다.
`--zed-depth` 를 주지 않으면 재생기는 지금과 똑같이 돕니다.

## 무엇을 흉내 내나

| 실기에서 생기는 것 | 시뮬레이션에서 넣는 방법 |
|---|---|
| ZED SDK 의 depth 계산 | 머리에 두 눈을 달아(두 눈 사이 63 mm) 그 두 그림을 실제 ZED SDK 5.5 의 NEURAL 모드에 넣습니다. depth 를 손으로 만든 노이즈로 흉내 내지 않습니다. |
| 카메라 값 | 정류된 그림의 K 를 실기 값으로 둡니다 (fx = fy 363.97, 중심 (336.5, 181.0) — 실기 (336.63, 180.86) 과 0.1 px 차이). |
| 렌즈 · 센서 | 렌즈 흐림(σ 0.6 px), 가장자리 어두워짐(모서리 20 %), 밝기에 따라 커지는 센서 잡음(중간 밝기에서 σ 약 3)을 프레임마다 넣습니다. |
| 조명 | 매장 조명의 세기(1.5–3.0 배)와 색온도(3500–6500 K)를 돌릴 때마다 무작위로 정합니다. |
| calibration 오차 | ZED SDK 에 알려 주는 두 눈 사이를 실제보다 1.5 % 크게 줍니다. 그래서 모든 거리가 약 1.5 % 멀게 읽힙니다. |

## 준비 — ZED 컨테이너

ZED SDK 는 `challenge_env` 가 아니라 따로 뜨는 컨테이너 `zed_depth` 에서 돕니다.

```bash
cd docker
docker compose -f docker-compose.yaml -f zed.yaml up -d
docker logs -f zed_depth        # "127.0.0.1:7300 에서 기다립니다" 가 나오면 준비가 끝난 것입니다
```

- NVIDIA 드라이버 **570 이상** (ZED SDK 이미지가 CUDA 12.8 입니다).
- 처음 한 번은 Stereolabs 의 ZED SDK 이미지를 받아 빌드하고(빌드된 이미지 약 20 GB), NEURAL 모델을 그 GPU 에 맞추느라 몇 분이 더
  걸립니다. 맞춘 결과는 `zed-resources` 볼륨에 남아 다음부터는 바로 뜹니다.
- GPU 메모리를 약 2.4 GB 더 씁니다.

## 돌리기

```bash
./run/run_zed_depth.sh b 0          # 과제 B 시연 0 번 (0~6)
./run/run_zed_depth.sh a            # 과제 A 기본 판
./run/run_zed_depth.sh c 0          # 과제 C 0 번
```

`run_zed_depth.sh` 는 두 컨테이너를 띄우고 depth 서버가 준비되기를 기다린 뒤, 화면 없이 재생기를 `--zed-depth` 로
돌립니다. 컨테이너 안에서 직접 돌려도 됩니다.

```bash
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u /workspace/challenge_scripts/task_b_replay.py \
    --seed 0 --headless --substeps 1 --hz 0 --zed-depth
```

과제 A · B 의 재생은 기록을 프레임마다 써 넣는 것이라 `--substeps 1 --hz 0` 으로 사이를 채우지 않는 편이 빠릅니다.
과제 C 는 물리로 다시 트는 재생이라 `--substeps` 를 바꾸지 않습니다. depth 는 한 프레임에 약 0.4 초가 걸립니다
(과제 B 한 판 8–19 분).

## 남는 것 — `workspace/zed_depth/<과제_판>/`

| 파일 | 내용 |
|---|---|
| `head_l/<프레임>.jpg` | ZED SDK 가 정류한 머리 왼쪽 그림 — depth 가 이 그림에 정합돼 있습니다 |
| `depth_zed/<프레임>.png` | 실기 방식 depth (16-bit PNG, mm, 0 = 값 없음) — 실기의 `head_l_depth` 와 같은 형식 |
| `depth_sim/<프레임>.png` | 같은 픽셀의 시뮬레이션 정답 depth (같은 형식) |
| `raw_l/<프레임>.jpg` | ZED SDK 에 보낸 왼쪽 그림 (50 프레임마다) |
| `compare.mp4` | 네 칸: head_l · 시뮬레이션 depth · ZED depth · ZED − 시뮬레이션 (±50 mm, 파랑 = ZED 가 가깝게, 빨강 = 멀게) |
| `stats.csv` | 프레임마다 3 m 안 픽셀의 \|ZED − 시뮬레이션\| 중앙값 · 90 % · 20 mm 넘게 다른 비율 · ZED 가 값을 못 낸 비율 |
| `summary.json` | 설정(조명 · 잡음 · 카메라)과 거리 구간별 차이 |

여러 판을 묶어 보려면:

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh /workspace/challenge_scripts/zed_depth/zed_summary.py /workspace/user/zed_depth
```

## 옵션

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--zed-depth` | 끔 | 켜면 위의 것을 남깁니다 |
| `--zed-server` | `127.0.0.1:7300` | depth 서버 주소 |
| `--zed-out` | `/workspace/user/zed_depth` | 남길 곳 |
| `--zed-every` | 1 | 기록 몇 프레임마다 depth 를 낼지 |
| `--zed-frames` | 0 (전부) | 앞에서 몇 번만 낼지 |
| `--zed-no-sensor` | — | 렌즈 흐림 · 가장자리 어두워짐 · 센서 잡음을 넣지 않습니다 |
| `--zed-no-video` | — | `compare.mp4` 를 만들지 않습니다 |
| `--light-scale LO HI` | 1.5 3.0 | 매장 조명 세기 배수의 범위. 3 배를 넘으면 흰 면이 하얗게 날기 시작합니다 |
| `--light-temp LO HI` | 3500 6500 | 색온도 범위 (K) |
| `--light-seed` | 무작위 | 같은 조명을 다시 내려면 로그에 찍힌 씨앗을 줍니다 |
| `--no-light-jitter` | — | 매장 조명을 바꾸지 않습니다 |

## 알아 둘 것

- 무늬 있는 면이 1.5 % 멀게 읽히는 것은 calibration 오차를 일부러 넣은 결과입니다. 실기에서 1–2 % 가 생기는 원인이
  같은지는 알 수 없습니다.
- 센서 잡음의 세기와 조명 범위는 실측한 값이 아니라 정한 값입니다.
- 실기 공지의 숫자(흰 판 먼 끝 +9 cm 등)는 공지 장면에서 잰 것이라, 매장 장면에서는 크기가 다르게 나옵니다.
- `head_l` 은 ZED SDK 가 정류한 그림이라, `--zed-depth` 없이 쓰는 시뮬레이션 머리 카메라(fx 367, 중심이 그림 한가운데)와
  화각이 조금 다릅니다.
- 정책을 붙여 돌리는 데모 평가 서버(`demo_server/`)에는 아직 붙이지 않았습니다.
