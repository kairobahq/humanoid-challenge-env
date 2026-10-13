# `scripts/taskD/` — 태스크 D 의 장면 규칙

> `scripts/README.md` 의 태스크 D 절이 요약이고, 이 문서가 파일별 역할과 설계 근거입니다.
> 환경 요소·생성 파라미터·좌표계는 [`docs/task_d.md`](../../docs/task_d.md) 에 있습니다.
>
> 태스크 D 는 **대회 과제가 아닌 모의 장면**입니다. 재생기와 채점기가 없습니다.

## 파일

| 파일 | 무엇 |
|---|---|
| `../task_d_demo.py` | 시작 장면 하나를 띄웁니다. `--seed --seconds --settle --shot --scene-json --no-clutter --check` |
| **`taskD_scene_seed.py`** | **시드 규칙 전부.** 시드 하나 → 선반·상자·배경 세 스트림. md5 파생 |
| `taskD_layout.py` | 자리와 에셋 경로. 시드와 무관한 것 전부. `CYCLOLAB_PATH` 우선 |
| `taskD_shelf.py` | 3 단 선반의 기하와 스폰. 판은 맨 위 한 장뿐 |
| `taskD_stock.py` | 맨 위 판에 무엇이 서고 어느 한 자리가 비는지. `attach(cfg, shelf_seed) -> int` |
| `taskD_crate.py` | 책상과 파란 상자, 그리고 상자에 든 하나. `attach(cfg, shelf_seed, crate_seed) -> int` |
| `taskD_clutter.py` | 배경 매장 집기. `attach(cfg, clutter_seed, cam_eyes) -> int` |
| `taskD_measured.json` | 자리와 치수의 **정본**. 숫자마다 `note` 에 근거와 날짜 |
| `store_fixtures.json` | 집기 20 종의 크기·중심·밑동 |
| `taskD_products.json` | 상품 36 종의 크기·밑동·진열 자세 |
| `taskD_stock_rules.json` | 칸 간격·잔떨림·필러 목록. 과제 B 에서 구운 값 |
| `bake_taskD_tables.py` | 위 세 JSON 을 `cyclo_lab` 에서 굽습니다. `--verify` 는 대조만 |
| `selftest_taskD.py` | 장면 규칙 자기 시험. **Isaac Sim 없이** 돕니다 |
| `shelf/` | 3 단 선반 USD 와 텍스처 (610 KB) |

## 설계 — 왜 이렇게 되어 있나

### 빈 자리와 상자는 한 뽑기의 두 면입니다

맨 위 판 3 열 중 한 열의 앞자리가 비고, **그 열의 상품이 그대로 상자에 들어갑니다.** 로봇이
채워야 하는 것이 바로 그 상품이므로 따로 뽑지 않습니다. 따로 뽑으면 "상자에 든 것과 빈 칸이
다른 상품" 이라는, 과제가 성립하지 않는 장면이 나옵니다. `taskD_stock.carried_item()` 한
곳에서만 나오고 `taskD_crate.py` 가 그것을 읽습니다.

### 시드는 md5 로 파생하고, 그 아래서는 `random` 을 씁니다

```
shelf_seed   = int(md5("taskD-eval-shelf|<seed>")[:8],   16) % 999999 + 1
crate_seed   = int(md5("taskD-eval-crate|<seed>")[:8],   16) % 999999 + 1
clutter_seed = int(md5("taskD-eval-clutter|<seed>")[:8], 16) % 999999 + 1
```

`random.Random(seed)` 는 파이썬 판이 바뀌면 다른 수열을 낼 수 있고 다른 언어에서는 재현할
방법이 없습니다. md5 는 파이썬이 없어도 같은 값이 나옵니다. **파생된 시드를 받은 뒤 모듈 안에서
`random.Random` 을 쓰는 것은 괜찮습니다** — 과제 A 도 그렇게 합니다(`taskA_seats.py:178`).
md5 로 막는 것은 주최 측과 참가자가 합의해야 하는 **최상위 파생**이고, 한 모듈 안에서 한 번
쓰이는 수열은 합의 대상이 아닙니다.

### 자리는 안 바뀌고 물건만 바뀝니다

로봇·책상·상자·선반의 좌표는 시드와 무관합니다(`taskD_layout.py`). 그래서 충돌 판정이 보는
발자국도 시드와 무관하고, 정책이 보는 그림만 매번 달라집니다. 과제 A 가 같은 규칙을 씁니다.

### 배경 집기는 기하로만 막습니다

집기는 운동학 고정이라 겹쳐도 PhysX 가 밀어내지 않고 **조용히 파고듭니다** — 눈으로는 틀렸고
로그로는 정상인 상태가 됩니다. 그래서 기하가 유일한 방어선입니다. 규칙 셋:

1. **작업영역 금지** — 로봇(실측 발자국 628 × 602 mm)·책상·상자·선반 네 상자에 여유 350 mm.
   상자는 `taskD_measured.json` 에서 **계산**합니다(손으로 적지 않습니다)
2. **카메라 눈에서 1.25 m 금지** — 없으면 렌즈 안에 냉장고가 생겨 화면이 텍스처 벽이 됩니다
3. **서로 겹침 금지** — 외접원으로 잽니다(yaw 를 일부러 비틀어 놓으므로)

어기는 추첨은 밀어내지 않고 **버리고 다시 뽑습니다.** 밀어내면 매번 선반에 딱 붙어 서게 되고
그것도 일종의 단서입니다.

### 장면 규칙 모듈은 순수 파이썬입니다

`isaaclab`·`numpy`·`pxr` 을 모듈 스코프에서 쓰지 않습니다. 그래서 `--check` 가 SimulationApp
없이 0.15 초에 끝나고 `selftest_taskD.py` 가 Isaac 없이 돕니다. 상품·집기 치수를 JSON 으로
구워 둔 이유가 이것입니다 — `cyclo_lab` 패키지를 모듈 스코프에서 import 하면 `isaaclab_tasks`
가 딸려 와 Isaac 밖에서 실패합니다. 과제 A 의 `taskA_shelf_stock.py` 가 `store_fixtures.json`
으로 같은 문제를 풀었고 그 방식을 따랐습니다.

### 선반 USD 가 이 폴더에 있는 이유

이 레포의 원칙은 **코드는 레포, 에셋은 이미지**이고 책상·상자·상품은 전부 릴리스
오버레이(`challenge-overlay.tar.gz`)로 갑니다. 태스크 D 의 선반만 아직 그 오버레이에 없어서,
넣어 줄 때까지 꾸러미가 스스로 돌 수 있게 사본을 들고 있습니다.

`taskD_layout.shelf_usd()` 가 **① 에셋 뿌리의 `fixtures/shelf_taskD/` → ② 이 폴더의
`shelf/` → ③ 개발 체크아웃** 순으로 봅니다. 그래서 오버레이에 들어가는 날 **코드는 한 줄도
고칠 필요가 없고**, 이 사본만 지우면 됩니다.

## 확인하는 법

```bash
# 장면 규칙 자기 시험 — Isaac 없이, 시드 500 전수
python3 scripts/taskD/selftest_taskD.py --seeds 500

# 구운 치수 표가 원본과 같은지 (cyclo_lab 체크아웃이 있을 때만)
python3 scripts/taskD/bake_taskD_tables.py --verify

# 모듈마다 혼자 돕니다
python3 scripts/taskD/taskD_scene_seed.py --seed 0 1 2 1000
python3 scripts/taskD/taskD_layout.py
python3 scripts/taskD/taskD_shelf.py
python3 scripts/taskD/taskD_stock.py  --shelf_seed 890328
python3 scripts/taskD/taskD_crate.py  --shelf_seed 890328 --crate_seed 969097
python3 scripts/taskD/taskD_clutter.py --clutter_seed 475037

# 장면 규칙과 에셋만 (SimulationApp 없이 1 초, Isaac 인터프리터는 필요)
${ISAACLAB_PATH}/_isaac_sim/python.sh -u /workspace/challenge_scripts/task_d_demo.py --check
```

`selftest_taskD.py` 가 지키는 것: 종속 랜덤(상자 = 빈 열 상품), 빈 자리가 실제로 빔, 같은 열
뒷줄에 같은 상품, 선반 5 개 전부 맨 위 판, 상자 상품이 안쪽·바닥 접촉·림 아래, 배경 집기 여유
전부 양수, 재현성. 새 규칙을 넣거나 문턱을 고칠 때 **이 파일이 먼저 깨져야 합니다.**
