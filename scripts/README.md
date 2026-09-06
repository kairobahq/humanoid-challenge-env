# scripts/ — 데모 스크립트

컨테이너의 `/workspace/challenge_scripts` 로 붙습니다. `git pull` 만 하면 컨테이너를
다시 만들지 않고 바로 돌릴 수 있습니다.

| 파일 | 하는 일 |
|---|---|
| `task_a_demo.py` | **과제 A 의 시작 장면**을 하나 만들어 띄웁니다 |
| `task_b_demo.py` | **과제 B 의 시작 장면**을 하나 만들어 띄웁니다 |
| `task_b_replay.py` | **과제 B 한 판 전부**를 처음부터 끝까지 틀어 줍니다 |
| `task_c_demo.py` | **과제 C 의 시작 장면**을 하나 만들어 띄웁니다 |
| `taskA/` | 과제 A 의 **장면 정의 모듈과 실측값**. 위 데모가 읽습니다 |
| `taskC/` | 과제 C 의 **장면 정의 모듈** — 상품 8 종, 계산대 위 배치 규칙, 검사. 위 데모가 읽습니다 |
| `demos/` | `task_b_replay.py` 가 트는 시연 기록 일곱 판 (2.4 MB) |

### 코드는 여기, 에셋은 이미지

과제 A 의 장면을 세우는 코드는 이 폴더 안에 있습니다.

```
scripts/taskA/
  taskA_seats.py        12 개 시식 좌석 -- 로봇이 어디 서고 바구니가 어디 놓이는지
  taskA_layout.py       목적지 진열대와 그 옆 책상, 로봇의 시작 자세
  taskA_stools.py       스툴을 좌석 반대편으로 치운다
  taskA_colliders.py    매장 집기의 콜라이더를 켠다 (USD 에는 꺼진 채로 실려 온다)
  taskA_robot_pose.py   로봇을 바로 세워 놓는다
  eatin_measured.json   시식 코너 실측값. 위 좌석이 여기서 나온다
  destinations.json     목적지와 책상 자리
```

**읽어 보셔도 됩니다.** 여러분의 정책이 마주할 장면이 정확히 어떻게 정해지는지가 그 안에
전부 적혀 있고, `git pull` 로 갱신됩니다.

**에셋은 배포 이미지에서 옵니다** — 매장 USD 184 MB, 로봇, 집기. 저장소에 둘 크기가 아니고,
매장 USD 는 참조 94 개를 상대경로로 물고 있어 통째로 옮겨야 합니다. 그래서 이 데모는
**저장소와 이미지가 둘 다 있어야** 돕니다. 이미지 주소는 `docker/.env` 의 `CHALLENGE_IMAGE`
입니다.

> 과제 B 는 장면 정의도 이미지 안에 있습니다(`taskB_*.py`). 과제 A 만 저장소에 두는 것은
> 매장 에셋이 워낙 커서 코드와 에셋을 갈라 놓는 편이 나았기 때문입니다.

과제 C 도 장면 정의를 저장소에 둡니다. 과제 A 와 같은 이유입니다.

```
scripts/taskC/
  taskC_products.py     상품 8 종 -- 코드용 이름, 사람이 읽는 이름, 원통/상자, 에셋 경로
  taskC_layout.py       계산대·로봇 시작 자세·빨간 띠·스캐너 자리·카메라 셋 -- 장면의 모든 수치
  taskC_deal.py         seed 로 상품 셋을 고르고 띠 안에 자리와 자세를 정한다 (QR 면은 -Y)
  taskC_check.py        가라앉은 상품이 규칙을 지켰는지 본다 -- 띠 안, 안 뚫림, 안 넘어짐, QR 방위, 간격
  taskC_report.py       터미널 요약과 --scene-json
  taskC_counter.py      빨간 띠를 그리고, 매장의 정적 스캐너·바구니를 끄고, 계산대 맨 아래 선반판을
                        잘라낸다 (Isaac 안에서만)
```

**에셋은 배포 이미지에서 옵니다** — 매장 USD 는 과제 A 와 같은 것이고, 여기에 QR 타일이
붙은 상품 8 종(`products_c/`, 각 `<이름>_phys.usd`)과 스캐너(`fixtures/scanner/`)가 더
옵니다. 상품 USD 는 QR 타일의 위치와 법선이 붙박여 있어서 과제 B 의 상품과 파일이 다릅니다.

---

## `task_a_demo.py`

```bash
# 컨테이너 안에서
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_a_demo.py --seed 1000
```

창이 뜨고, 그 안에 과제 A 의 **에피소드가 시작되는 순간**이 서 있습니다. 여기서
멈춥니다. 집지도, 몰지도, 놓지도 않습니다. 여러분의 정책이 첫 관측으로 받게 될 그림을
그대로 보여 주는 것이 목적입니다.

### 장면에 있는 것

**매장** — 편의점 전체가 들어옵니다. 통로 세 줄, 곤돌라, 냉장고, 냉동고, 와인 진열대,
계산대, 그리고 시식 코너. 과제 B 가 진열대 하나 앞에서 벌어지는 것과 달리 과제 A 는
**매장을 가로지릅니다** — 좌석에 따라 목적지까지 직선으로 9.3 ~ 11.2 m 이고, 통로를
돌아가야 하므로 실제 경로는 그보다 깁니다.

**시식 탁상과 좌석** — 원형 탁상 3 개를 4 등분한 **12 개 고정 좌석** 중 하나에서
시작합니다. 매장 어디서나 임의로 출발하던 예전 정의는 폐기됐습니다. 로봇은 좌석에서
탁상 쪽으로 300 mm 나온 자리에 서고, 그 자리는 탁상 중심에서 0.624 m 입니다 — 탁상
반지름(0.524)과 로봇 반지름(0.281)을 더한 0.805 보다 안쪽이라 **여기서는 제자리
회전을 할 수 없습니다.** 집은 뒤에 먼저 물러나야 돌 수 있습니다.

**바구니** — 탁상 위 파란 상자(0.380 × 0.590 × 0.140 m). 이것을 집어서 가져가야
합니다. 긴 면이 로봇을 향하도록 놓입니다.

**스툴** — 이 탁상의 스툴 넷은 로봇의 **반대편으로 치워져** 있습니다. 매장이 지어질
때는 시드마다 다른 각도로 흩어지는데, 그대로 두면 둘이 로봇이 설 자리에 걸터앉습니다.
치운 뒤에도 로봇에서 0.55 m 이상 떨어져 있어야 베이스가 제자리 회전을 끝낼 수 있습니다.
그 0.55 m 는 실측에서 나온 값이지만, 환경 코드(`taskA_seats.py`)가 **잠정값으로 표시해
두었습니다** — 잰 당시 로봇이 바로 서 있지 않았을 가능성이 있어 다시 재기 전까지는
그렇게 봅니다.

**목적지와 책상** — 목표 진열대 앞의 도착 자리, 그리고 그 옆 책상. 바구니는 그 책상
위에 놓여야 합니다. **장면에 책상은 하나뿐입니다.**

**로봇** — 몸통을 이미 작업 높이(-0.060)까지 내리고 고개를 39.8도 숙인, 집기 직전
자세로 섭니다. **바퀴가 바닥에 닿아 있습니다** — 공중에서 떨어지지도, 바닥을 뚫지도
않습니다. 돌리면 실제로 잰 바퀴 높이를 찍어 줍니다.

**카메라** — 채점이 정책에게 보내는 관측은 세 대입니다: 머리 `head_l`(672×376,
실기 ZED 좌안)과 양 손목 `wrist_l`/`wrist_r`(424×240, D405). 이 데모 스크립트는
아직 옛 구성을 스폰하며, 씬 생성기 교체와 함께 이 값으로 맞춰집니다. 과제 B 와 같습니다.

> 주행 관측(LiDAR `scan`)은 이 데모에 없습니다. 별도 마일스톤으로 따로 들어옵니다.

### 장면 하나는 seed 하나가 정합니다

`--seed` 가 같으면 어디서 몇 번을 돌려도 같은 장면입니다. 어느 좌석에서 시작하는지,
그리고 로봇이 쓰지 않는 나머지 두 탁상의 스툴이 어떻게 흩어지는지가 그 수에서 나옵니다.

로봇이 앉는 탁상의 스툴 넷은 좌석이 정합니다 — 좌석 반대편으로 치운다는 규칙이 정하는
것이라 난수를 섞지 않습니다. 그래서 `--seat` 이 같으면 그 넷은 seed 와 무관하게 같습니다.

```bash
--seed 1000        # 이 장면 (좌석 8)
--seed 1001        # 다른 장면
--seat 3           # 좌석을 직접 고릅니다 (0~11). 그냥 두면 seed 가 고릅니다
```

### 옵션

| 옵션 | 뜻 |
|---|---|
| `--seed N` | 장면을 정하는 수 (기본 1000) |
| `--seat {0..11}` | 좌석을 직접 고릅니다. 탁상 0/1/2 의 순서로 0~11 번입니다 |
| `--seconds S` | S 초 동안 세워 두고 끝냅니다. 0 이면 창을 닫을 때까지 |
| `--headless` | 화면 없이 돌립니다 |
| `--scene-json FILE` | 장면 내용을 JSON 으로 저장합니다 |
| `--shot FILE.png` | 로봇 머리 카메라가 보는 그림을 한 장 저장합니다 |
| `--check` | **좌석 기하와 매장 USD 만 검사하고 끝냅니다.** Isaac Sim 을 띄우지 않아 1 초면 됩니다 |

### 먼저 `--check` 로 확인하기

시뮬레이터를 띄우는 데 매장까지 읽으면 시간이 걸립니다. 좌석이 벽 안에 있거나 스툴이
회전을 막는 종류의 문제는 그 전에 알 수 있습니다.

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_a_demo.py --check
```

```
[검사] 12 좌석의 기하 -- Isaac Sim 없이

  table_radius   0.5242
  table_top_z    0.7500
  stool_radius   0.1883
  stool_dist     0.3922
  standoff       0.9242

  좌석  0  탁상0  45.0도  로봇 ( -9.309,   4.341) yaw  -135.0  목적지까지  9.379 m
  좌석  1  탁상0 135.0도  로봇 (-10.191,   4.341) yaw   -45.0  목적지까지 10.247 m
  ...
  좌석 11  탁상2 315.0도  로봇 ( -9.309,  -2.341) yaw  +135.0  목적지까지 10.431 m

  매장 USD: /workspace/cyclo_lab/source/cyclo_lab/data/store/scene/fixture_kit/out/store_scene.usd

  판정: 문제 없음
```

좌석 기하뿐 아니라 **매장 USD 가 제자리에 있는지도** 봅니다. 문제가 있으면 `판정:` 줄
다음에 `!` 로 시작하는 줄로 하나씩 찍히고 종료 코드가 1 이 됩니다.

### 장면을 글로 받기

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_a_demo.py --seed 1000 --headless \
    --seconds 1 --scene-json /workspace/user/scene_a_1000.json
```

터미널에 좌석과 로봇 자세, 바구니 좌표, 목적지와 책상, 스툴 자리가 찍히고 같은 내용이
JSON 으로 남습니다. `/workspace/user` 는 호스트의 `workspace/` 라서 컨테이너 밖에서
바로 열립니다.

```
[장면] seed 1000, 좌석 8 (탁상 2 의 45도 자리)

  로봇 -- 좌석에서 앞으로 나와 탁상을 마주 본다
    자리      (-9.309, -1.459)  yaw -135.0 도
    탁상까지  중심에서 0.624 m (좌석은 0.924, 여기서 0.300 앞으로 나왔다)
    몸통      -0.0600    고개 39.8 도 아래

  집을 것 -- 탁상 위 파란 바구니
    바구니    (-9.609, -1.759, 0.750)  yaw +45.0 도
    크기      0.380 x 0.590 x 0.140 m
    탁상      중심 (-9.750, -1.900)  반지름 0.5242  상판 0.7500

  가져갈 곳 -- 목적지 진열대와 그 옆 책상
    도착 자리 (-0.100, +2.559)  yaw +0.0 도
    책상      (+0.162, +1.698)  상판 0.725 m  -- 도착 자리에서 0.900 m
    직선거리  로봇에서 10.047 m (실제 경로는 통로를 돌아가므로 이보다 길다)

  이 탁상의 스툴 -- 좌석 반대편으로 치워 둔다
    0: (-9.651, -2.224)  로봇에서 0.839 m
    1: (-10.066, -1.758)  로봇에서 0.814 m
    2: (-9.873, -2.272)  로봇에서 0.990 m
    3: (-9.525, -2.221)  로봇에서 0.793 m
    회전 실측 기준 0.55 m 이상 -- 이보다 가까우면 베이스가 제자리 회전을 못 끝낸다
```

장면이 다 서면 실제로 잰 값들을 찍어 줍니다. **바퀴가 바닥에 닿았는지**와 **로봇이 서
있는지**가 여기서 확인됩니다 -- 누운 로봇에서 잰 숫자는 틀린 숫자가 아니라 다른 질문에
대한 답이라, 물어보는 편이 낫습니다.

```
[i] 좌석 8 -- 탁상 2 의 45도 자리
[i] 로봇 시작 자세  x -9.3067  y -1.4552  yaw -135.00 deg  몸통 -0.0608
[i] 가장 낮은 바퀴 중심 0.0883 m, 반지름 0.0864 -> 바닥과 +1.9 mm. 닿아 있다
[i] 기울기 0.0도, 위쪽 축 (-0.000, 0.001, 1.000) -> 서 있음
[i] 바구니  (-9.6086, -1.7586, 0.7500) -- 탁상 상판 0.7500 위에 놓여 있다
[i] 목적지까지 직선 10.043 m
[i] 장면이 섰다. 여기서 과제 A 가 시작한다.
```

### 화면 없이 장면을 눈으로 보기

`--shot` 을 붙이면 로봇 머리 카메라가 보는 그림 한 장이 저장됩니다. 여러분의 정책이
첫 관측으로 받게 될 바로 그 그림입니다.

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_a_demo.py --seed 1000 --headless \
    --seconds 1 --shot /workspace/user/shot_a_1000.png
```

### 좌표

바닥이 z = 0 입니다. 매장은 x 가 -11.1 ~ 1.3, y 가 -5.12 ~ 7.25 이고 **통로는 Y
방향**입니다. 시식 코너는 매장 서쪽(-X)에, 목표 진열대는 동쪽 끝(원점 근처)에
있습니다. 그래서 한 에피소드는 매장을 서에서 동으로 가로지릅니다.

에셋이 어디에 어떤 이름으로 놓여 있는지는 루트 [`README.md`](../README.md) 의
**환경 안의 에셋** 절에 있습니다.

---

## `task_b_demo.py`

```bash
# 컨테이너 안에서
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_b_demo.py --seed 1000
```

창이 뜨고, 그 안에 과제 B 의 **에피소드가 시작되는 순간**이 서 있습니다. 여기서
멈춥니다. 집지도, 놓지도, 움직이지도 않습니다. 여러분의 정책이 첫 관측으로 받게 될
그림을 그대로 보여 주는 것이 목적입니다.

### 장면에 있는 것

**진열대** — 다섯 단이 상품으로 차 있습니다. 위 두 단(3단과 2단)의 앞줄 중 **한 칸이
비어 있습니다.** 비어 있는 칸 뒤에는 그 칸에 들어갈 상품이 서 있어서, 무엇을 채워야
하는지는 진열대를 보면 알 수 있습니다. `--gaps` 로 두 칸·세 칸까지 늘립니다.

**책상 위 파란 상자** — 빈 칸 수만큼 상품이 들어 있습니다. 상자의 첫 번째 상품이
첫 번째 빈 칸으로, 두 번째가 두 번째 빈 칸으로 갑니다.

**로봇** — 상자를 마주 보고 섭니다. 시연을 모을 때 로봇이 서던 그 자세 그대로입니다:
베이스 (-0.280, -0.276), yaw -87.3 도, 몸통 높이 -0.22 m, 고개 28 도 숙임, 양팔은
곧게 편 채 어깨만 20 도 벌림. 진열대는 이 자세에서 뒤쪽에 있으므로, 어느 칸이 비었는지
보려면 로봇이 몸을 돌려야 합니다. 값은 `task_b_demo.py` 의 `START_*` 상수에 있고,
출처는 그 옆 주석이 적어 둡니다.

**카메라** — 채점이 정책에게 보내는 관측은 세 대입니다: 머리 `head_l`(672×376,
실기 ZED 좌안)과 양 손목 `wrist_l`/`wrist_r`(424×240, D405). 이 데모 스크립트는
아직 옛 구성을 스폰하며, 씬 생성기 교체와 함께 이 값으로 맞춰집니다.

### 상품 이름은 두 가지입니다

상품 하나에 이름이 둘 붙어 있고, 쓰이는 곳이 다릅니다.

| | 예 | 어디에 나오나 |
|---|---|---|
| 코드용 이름 | `pringles_original_small` | 상품 폴더와 그 안의 USD 파일 이름, `manifest.json` · `orientation.json` · `display_yaw.json` · `shapes.json` 의 키, 장면 JSON 의 `product` |
| 영어 이름 | `small original Pringles tube` | 로봇에게 주는 지시문, 장면 JSON 의 `label` |

코드용 이름 하나로 그 상품의 모든 것이 이어집니다. 상품을 하나 정했으면 이 이름으로
에셋과 설정을 전부 찾을 수 있습니다.

```
products/pringles_original_small/pringles_original_small.usd   스폰되는 USD
manifest.json    의 "pringles_original_small"                  크기 · 무게 · 콜라이더
orientation.json 의 "pringles_original_small"                  어느 면이 위인가
display_yaw.json 의 "pringles_original_small"                  진열될 때 몇 도 돌아가는가
shapes.json      의 "pringles_original_small"                  상자인가 원통인가
```

영어 이름은 사람에게 보여 주는 쪽입니다. 로봇에게 주는 지시문에 이 이름이 들어갑니다.
시연 기록에 실려 있는 문장이 이렇습니다.

```
take the Buldak stir-fried noodle cup out of the crate and put it into the empty slot on the shelf
```

### `--gaps` 와 `--seed`

장면 하나는 이 두 값으로 정해집니다. `--gaps` 는 진열대에서 몇 칸을 비울지, `--seed` 는
그렇게 비운 장면 중 몇 번째 것을 볼지입니다.

`--gaps` 는 1, 2, 3 중 하나이고 아무것도 안 쓰면 1 입니다. 빈 칸 하나에 상자 속 상품
하나가 짝지어지므로, 두 칸을 비우면 상자에 상품이 두 개 들어가고 로봇은 두 번 옮깁니다.
빈 칸이 둘 이상이어도 한 열에서 두 칸이 비지는 않고, 상자에 같은 상품이 두 개 들어가지도
않습니다.

`--seed` 는 장면 번호입니다. 같은 `--gaps` 와 같은 `--seed` 를 넣으면 언제나 똑같은
장면이 나옵니다. 어느 컴퓨터에서 돌려도 그렇습니다.

둘 중 하나만 바꿔도 장면은 통째로 새로 뽑힙니다. 어느 칸이 비는지, 상자에 무슨 상품이
들어가는지, 나머지 칸에 무엇이 놓이는지, 책상이 어느 쪽을 보는지가 전부 달라집니다.
있던 장면에 빈 칸 하나가 더 생기는 것이 아닙니다.

### 예시

```bash
--gaps 1 --seed 1000    # 2단 앞줄 칸1 이 빈다.       상자: small original Pringles tube
--gaps 1 --seed 1001    # 3단 앞줄 칸0 이 빈다.       상자: Chocobi snack box
--gaps 2 --seed 1001    # 2단 앞줄 칸1 과 칸0 이 빈다. 상자: baked potato snack box,
                        #                            ABC chocolate cookie box
```

같은 1001 번이라도 빈 칸이 1 에서 2 로 바뀌면 비는 자리가 3단에서 2단으로 옮겨 가고,
상자에 있던 Chocobi 는 아예 나오지 않습니다.

### 창을 띄우지 않고 장면 확인하기

창을 열지 않고도 그 장면에 무엇이 있는지 알 수 있습니다.

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_b_demo.py --seed 1000 --headless \
    --seconds 1 --scene-json /workspace/user/scene_1000.json
```

`--scene-json` 을 주면 진열대 각 칸의 상품과 좌표, 비어 있는 칸, 상자 속 상품이 JSON
파일 하나로 저장됩니다. `/workspace/user` 는 호스트의 `workspace/` 폴더라서, 저장된
파일은 컨테이너 밖에서 바로 열립니다.

JSON 과 같은 내용이 터미널에도 찍힙니다.

```
[장면] seed 1000, 빈 칸 1 개

  진열대 -- 단/줄/칸, 앞줄(row 0)이 손님 쪽
    3단  (판 높이 1.155 m)
      줄0 칸0  strawberry Oreo box           (+0.575, -0.276, 1.269)  [oreo_strawberry]
      줄0 칸1  Maxim coffee mix box          (+0.575, +0.004, 1.247)  [maxim_coffee]
      줄0 칸2  baked sweet potato snack box  (+0.572, +0.277, 1.239)  [guun_goguma]
      줄1 칸0  strawberry Oreo box           (+0.708, -0.283, 1.269)  [oreo_strawberry]
    2단  (판 높이 0.746 m)
      ...

  비어 있는 칸 -- 상자 속 i 번째 상품이 i 번째 칸에 들어간다
    0: 2단 줄0 칸1  <- small original Pringles tube  [pringles_original_small]

  상자 속 상품
    0: small original Pringles tube  (-0.252, -0.801, 0.788)  [pringles_original_small]

  상자 -0.282, -0.855, 0.727    책상 -0.282, -0.903    진열대 앞면 x = 0.470
```

출력에서 앞의 `small original Pringles tube` 가 영어 이름이고, 대괄호 안의
`pringles_original_small` 이 코드용 이름입니다.

### 화면 없이 장면을 눈으로 보기

`--shot` 을 붙이면 로봇 머리 카메라가 보는 그림 한 장이 저장됩니다. 여러분의 정책이
첫 관측으로 받게 될 바로 그 그림입니다.

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_b_demo.py --seed 1000 --headless \
    --seconds 1 --shot /workspace/user/shot_1000.png
```

### 좌표

바닥이 z = 0 입니다. 진열대는 -X 를 보고 서 있고 그 **앞면이 x = 0.470** 입니다.
로봇은 원점 근처에서 상자를 마주 봅니다. 책상과 상자는 로봇의 -Y 쪽에 있습니다.

에셋이 어디에 어떤 이름으로 놓여 있는지는 루트 [`README.md`](../README.md) 의
**환경 안의 에셋** 절에 있습니다.

---

## `task_b_replay.py`

`task_b_demo.py` 는 시작 장면에서 멈춥니다. 이 스크립트는 **그 다음**을 보여 줍니다 --
로봇이 상자에서 상품을 꺼내고, 몸을 돌려 진열대로 가서, 빈 칸에 놓는 한 판 전부입니다.

```bash
# 컨테이너 안에서
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_b_replay.py --seed 1
```

호스트에서 한 줄로 띄우려면 `run/run_task_b_replay.sh` 를 쓰세요.

### 들어 있는 판

`--seed 0` 부터 `--seed 6` 까지 일곱 판입니다. `--list` 로 목록을 봅니다.

| `--seed` | 상품 | 어느 칸에 | 길이 |
|---:|---|---|---:|
| 0 | Buldak stir-fried noodle cup | the third shelf, left column | 116 초 |
| 1 | small sour cream Pringles tube | the third shelf, middle column | 273 초 |
| 2 | Yegam original potato chip tube | the third shelf, right column | 120 초 |
| 3 | baked sweet potato snack box | the third shelf, right column | 107 초 |
| 4 | Jin Ramen hot cup | the third shelf, middle column | 111 초 |
| 5 | Butter Ring biscuit box | the third shelf, middle column | 120 초 |
| 6 | Cereal Choco biscuit box | the third shelf, left column | 114 초 |

`task_b_demo.py` 의 `--seed` 는 **장면을 뽑는 수**지만, 여기서는 **어느 기록을 트는지**
고르는 번호입니다. 이 일곱 판은 미리 모아 둔 것이라 새로 뽑히지 않습니다.

### 이것은 재생입니다

프레임마다 로봇의 관절 31 개와 로봇의 위치, 그리고 상품 스물다섯 개의 위치를 기록에서
그대로 **써 넣습니다.** 그래서 나뉘는 것이 있습니다.

* **정확한 것** — 로봇이 어디 있었는지, 상품이 어디 있었는지. 전부 실제로 일어난 그
  값입니다.
* **보여 줄 수 없는 것** — 접촉. 손가락이 상품을 눌러 딸려 오는 것이 아니라 상품도
  제자리에 놓입니다. "이 파지가 미끄러지지 않고 버티는가" 는 이 화면이 답할 수 있는
  질문이 아닙니다. 그건 이 판을 실제로 돌려서 이미 답한 것이고, 일곱 판 모두 놓기에
  성공한 판입니다.

### 재생 중 점수가 찍힙니다

과제 B 평가표(상품 하나 15항목 30점)대로 `taskb_score.py` 가 이 기록을 채점하고, 재생 중
그 일이 일어나는 프레임에 `[점수]` 줄로 알립니다. 점수는 화면이 아니라 **기록(npz)에서**
나오므로 `--substeps`·`--hz` 와 무관하게 같습니다.

```
[점수] 채점 대상 samyang_buldak_cup → 목표 칸 L2 c2 · 평가표 15항목 30점
[점수]    8.3초  product 에 닿았는가             +1   누적  1/30
[점수]   10.3초  product 를 들어올렸는가           +2   누적  3/30
[점수]   10.4초  product 를 상자 밖으로 꺼냈는가     +3   누적  6/30
   ...
[점수]  113.3초  ── 놓은 뒤 3초 ──
[점수]          목표 층에 올렸는가              +2/2   층 2 밑면 -1 mm
[점수]          어느 칸에 넣었는가              +4/4   칸 (2, 2) 좌우 -3 mm
   ...
[점수] ════ 최종 29 / 30 점 ════
```

* **[한 번이라도]** 항목(닿았는가 · 들어올렸는가 · 상자 밖 · 선반 앞 · 목표 층 높이 · 목표 칸 앞)은
  판이 도는 내내 보고 처음 참이 된 순간에 알립니다. 뒤에 무슨 일이 생겨도 뺏지 않습니다.
* **놓은 뒤 3초** 항목(떨어뜨리지 않았는가 · 목표 층 · 어느 칸 · 서 있는가 · 방향 · 앞줄 · 멈춤 ·
  상자 제자리 · 다른 상품 그대로)은 잡고 있던 손의 gripper 가 열린 프레임 + 3초에 한 번 봅니다.
* 상품이 바닥·탁자·상자에 떨어져 3초 멈추면 **그 순간 채점이 끝나고** 그 뒤는 보지 않습니다.
  다시 주워 놓아도 점수가 없습니다.

`taskb_score.py` 는 혼자서도 돕니다 -- `python3 taskb_score.py demos/demo_00.npz` 가 같은 표를
찍습니다 (Isaac 없이, numpy 만).

### 옵션

```bash
--seed 1          어느 판 (0..6)
--substeps 4      기록된 자세 사이를 몇 배로 채우나. 1 이면 안 채운다
--hz 40           초당 몇 장까지 그리나. substeps 와 곱이 10 이면 실제 속도
--hz 20           절반 속도로 천천히
--list            무슨 판이 들어 있는지 찍고 끝낸다
```

기록은 **10 Hz** 입니다. 그대로 그리면 눈에 뚝뚝 끊겨 보여서, 자세와 자세 사이를
`--substeps` 배로 채워 그립니다. 채우는 값은 양 끝을 잇는 것일 뿐이고, 끝점은 언제나
기록입니다.

### 배경(매장)은 없습니다

이 기록은 매장 안에서 모았지만 배포 이미지에는 매장 USD 가 들어 있지 않습니다.
로봇·진열대·책상·상자·상품은 기록 그대로이고, 주위의 가게만 비어 있습니다.

---

## `task_c_demo.py`

```bash
# 컨테이너 안에서
cd /workspace/cyclo_lab
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_c_demo.py --seed 1000
```

창이 뜨고, 그 안에 과제 C 의 **에피소드가 시작되는 순간**이 서 있습니다. 여기서
멈춥니다. 집지도, 비추지도, 놓지도 않습니다.

### 장면에 있는 것

**매장** — 과제 A 와 같은 편의점 전체. 장면은 계산대 앞이고 로봇은 주행하지 않습니다.
조명은 매장 USD 의 것(돔 + 천장 램프)만 씁니다 — 학습 데이터를 찍은 조명 그대로입니다.

**계산대 위 빨간 띠** — 로봇 좌표로 앞 0.110 ~ 0.500 m, 왼쪽 -0.010 ~ 0.570 m 의
사각형을 20 mm 빨간 테이프로 두른 자리입니다. 상판 높이는 0.9035 m. 계산대 직원 쪽 맨
아래 선반판(바닥 위 10 cm)은 로봇 섀시가 올라타지 않도록 잘라냅니다(학습 데이터와 동일).

**상품 셋** — 8 종 가운데 seed 가 고른 셋. 슬롯 0 이 집을 상품입니다. 놓이는 규칙:

| 규칙 | 값 |
|---|---|
| QR 면 방위 | 로봇의 정 오른쪽(세계 -Y). 오차 3 도 안 |
| 원통(프링글스·컵·캔) | 서 있음. 절반은 뒤집어 세움(QR 이 상하 반전) |
| 상자(예감·롯데샌드) | 눕힘. QR 면이 옆을 봄 |
| 상품 간격 | 10 cm 이상 (회전한 바닥면 기준) |
| 스폰 뒤 | 3 초 물리 정착. 규칙을 어기면 같은 seed 안에서 재딜 (최대 50 회) |

**스캐너** — 왼손이 드는 자리 (로봇 좌표 0.330, -0.158, 1.161) 에 중력 없이 떠 있습니다.
매장 USD 에 놓여 있던 정적 스캐너 소품과 계산대 옆 바구니는 이 데모가 끕니다.

**로봇** — 계산대 앞 (-3.45, -4.27) 에서 +Y 를 봅니다. 몸통 0.0, 고개 39.8 도 아래,
양팔 스토우. 바퀴가 바닥에 닿아 있습니다.

**카메라** — 머리 `head_cam` 672×376, 손목 `left_wrist_cam`/`right_wrist_cam` 424×240.

### 상품 이름

| 코드용 이름 | 사람이 읽는 이름 | 모양 |
|---|---|---|
| `pringles_original_small` | small original Pringles tube | 원통 |
| `pringles_sourcream_small` | small sour cream Pringles tube | 원통 |
| `ottogi_cupnoodle_buldak` | Ottogi Buldak cup noodle | 원통 |
| `samyang_buldak_cup` | Buldak stir-fried noodle cup | 원통 |
| `chilsung_cider` | Chilsung cider can | 원통 |
| `cocacola_zero` | Coca-Cola zero can | 원통 |
| `yegam_original` | Yegam original potato chip tube | 상자 |
| `lotte_sand` | Lotte Sand biscuit box | 상자 |

### 옵션

| 옵션 | 뜻 |
|---|---|
| `--seed N` | 장면을 정하는 수 (기본 1000) |
| `--products a,b,c` | 상품 셋을 코드용 이름으로 직접 고릅니다. 첫 번째가 집을 상품 |
| `--seconds S` | S 초 동안 세워 두고 끝냅니다. 0 이면 창을 닫을 때까지 (`--headless` 면 1 초) |
| `--headless` | 화면 없이 돌립니다 |
| `--scene-json FILE` | 장면 내용을 JSON 으로 저장합니다 |
| `--shot FILE.png` | 로봇 머리 카메라가 보는 그림을 한 장 저장합니다 |
| `--check` | **에셋과 띠 기하만 검사하고 끝냅니다.** Isaac Sim 을 띄우지 않아 1 초면 됩니다 |

### 먼저 `--check` 로 확인하기

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_c_demo.py --check
```

```
[검사] 과제 C 장면 기하와 에셋 -- Isaac Sim 없이

  계산대    중심 (-4.000, -4.220)  상판 0.9035  크기 3.233 x 1.800
  로봇      (-3.450, -4.270)  yaw +90.0 도  몸통 +0.000  고개 39.8 도 아래
  빨간 띠   로봇 좌표 x 0.1101~0.4999  y -0.010~0.570  (테이프 20 mm 안쪽 x 0.130~0.480  y 0.010~0.550)
  상품 8 종  /workspace/cyclo_lab/source/cyclo_lab/data/products_c
    pringles_original_small    small original Pringles tube        71.7 x  71.7 x 101.0 mm  원통  O
    pringles_sourcream_small   small sour cream Pringles tube      71.7 x  71.7 x 101.1 mm  원통  O
    ottogi_cupnoodle_buldak    Ottogi Buldak cup noodle           101.5 x 101.5 x 102.2 mm  원통  O
    yegam_original             Yegam original potato chip tube     55.0 x 210.0 x  55.0 mm  상자  O
    samyang_buldak_cup         Buldak stir-fried noodle cup       102.5 x 102.5 x 110.9 mm  원통  O
    chilsung_cider             Chilsung cider can                  66.1 x  66.3 x 125.2 mm  원통  O
    cocacola_zero              Coca-Cola zero can                  65.9 x  65.9 x 122.8 mm  원통  O
    lotte_sand                 Lotte Sand biscuit box              48.0 x 225.0 x  48.0 mm  상자  O
  스캐너 USD /workspace/cyclo_lab/source/cyclo_lab/data/fixtures/scanner/scanner_taskC.usd
  매장 USD  /workspace/cyclo_lab/source/cyclo_lab/data/store/scene/fixture_kit/out/store_scene.usd

  판정: 문제 없음
```

상품 8 종의 USD 와 QR 타일 정보, 스캐너 USD, 매장 USD 가 제자리에 있는지 봅니다. 문제가
있으면 `판정:` 줄 다음에 `!` 로 시작하는 줄로 하나씩 찍히고 종료 코드가 1 이 됩니다.

### 장면을 글로 받기

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_c_demo.py --seed 1000 --headless --seconds 1 \
    --scene-json /workspace/user/scene_c_1000.json
```

```
[장면] seed 1000, 집을 것 small original Pringles tube [pringles_original_small]

  로봇 -- 계산대를 마주 보고 선다 (정지 과제: 주행하지 않는다)
    자리      (-3.449, -4.274)  yaw +90.0 도
    몸통      +0.0000    고개 39.8 도 아래    양팔 스토우 (오른팔 joint1 1.200)
    계산대    중심 (-4.000, -4.220)  상판 0.9035 m

  계산대 위 상품 -- 슬롯 0 이 집을 상품, QR 면은 정 오른쪽(-Y)을 본다
    0: small original Pringles tube     (-3.877, -3.853, 0.954)  [pringles_original_small] 직립  QR 오차 0.0 도  최근접 13.3 cm
    1: Lotte Sand biscuit box           (-3.496, -3.941, 0.927)  [lotte_sand] 눕힘  QR 오차 0.0 도  최근접 31.7 cm
    2: small sour cream Pringles tube   (-3.950, -4.075, 0.954)  [pringles_sourcream_small] 직립  QR 오차 0.0 도  최근접 13.3 cm

  빨간 띠(로봇 좌표)  x 0.110~0.500  y -0.010~0.570  테이프 20 mm  -- 상품끼리 10 cm 이상
  스캐너    왼손이 드는 자리 (-3.292, -3.940, 1.161)  크기 0.067 x 0.161 x 0.087 m
  카메라    head_cam 672x376, left_wrist_cam 424x240, right_wrist_cam 424x240
  재딜      0 회

[i] 로봇 시작 자세  x -3.4489  y -4.2736  yaw +90.00 deg  몸통 -0.0262
[i] 가장 낮은 바퀴 중심 0.0883 m, 반지름 0.0864 -> 바닥과 +1.9 mm. 닿아 있다
[i] 기울기 0.0도, 위쪽 축 (0.001, -0.000, 1.000) -> 서 있음
[i] 상품 0 pringles_original_small  (-3.8770, -3.8533, 0.9539)  상판 위  띠 안
[i] 상품 1 lotte_sand  (-3.4963, -3.9412, 0.9274)  상판 위  띠 안
[i] 상품 2 pringles_sourcream_small  (-3.9499, -4.0753, 0.9539)  상판 위  띠 안
[i] 스캐너  (-3.2922, -3.9400, 1.1610) -- 왼손이 드는 자리
[i] 장면이 섰다. 여기서 과제 C 가 시작한다.
```

JSON 에는 같은 내용이 들어 있습니다. 상품마다 `pos`(세계)·`pos_robot`(로봇 좌표: x 앞,
y 왼쪽)·`quat`·`quat_robot`·`cylinder`·`qr_az_err_deg`·`gap_min_m`, 그리고 `band`,
`counter`, `robot`, `scanner`, `cameras`, `redeal`.

### 화면 없이 장면을 눈으로 보기

```bash
${ISAACLAB_PATH}/_isaac_sim/python.sh -u \
    /workspace/challenge_scripts/task_c_demo.py --seed 1000 --headless \
    --seconds 1 --shot /workspace/user/shot_c_1000.png
```

### 좌표

바닥이 z = 0 이고 매장 좌표는 과제 A 와 같습니다. 계산대 중심 (-4.00, -4.22), 상판
0.9035 m. 로봇 좌표는 로봇 발 밑이 원점, x 가 앞(세계 +Y), y 가 왼쪽(세계 -X)입니다.
`taskC_layout.py` 의 `robot_to_world` / `world_to_robot` 이 그 변환입니다.
