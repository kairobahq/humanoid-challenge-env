# selfcoll — 실기 자기 충돌 사전 검사기

실기 본선에서 평가 대시보드가 쓰는 **자기 충돌 사전 검사(Pre-execution Check)** 코드입니다.
정책이 보낸 액션 청크를 로봇에서 실행하기 **전에**, 실제로 보낼 궤적 전체에서 로봇 부품끼리 너무 가까워지는지 판정합니다.
같은 코드로 여러분의 정책 출력을 미리 검사해 볼 수 있습니다.

## 판정 기준

허용 거리: **d ≥ 기본 여유 + 0.02 s × v** (v = 두 부품이 서로 가까워질 수 있는 상대 속도 상한, m/s)

| 부품 쌍 | 기본 여유 |
|---|---|
| 그리퍼·손 ↔ 몸통, 머리, 베이스, 다른 팔 / 팔 ↔ 몸통, 머리, 베이스, 다른 팔 | **3 cm** |
| 같은 팔의 링크끼리 (link1–7) | 2 cm |
| 팔 link5 ↔ 같은 손 그리퍼 손가락, 팔 link6 ↔ 같은 손 그리퍼 몸체 | 2 cm |
| 리프트 기둥 ↔ 머리 (head_link1, head_link2, ZED) | 2 cm |

| 판정 | 조건 | 대시보드 동작 |
|---|---|---|
| `pass` | 경로 전체가 허용 거리를 지킴 | 청크 전체 실행 |
| `truncate` | 경로 중간에 어김 | 어기기 전에 도착하는 점까지 잘라 궤적을 **다시 만들어** 재검사, 통과한 앞부분만 실행 |
| `reject` | 실행할 수 있는 앞부분이 없음 | 직전 목표 자세 1틱 유지 → 다음 추론 |

- 이미 허용 거리 안에서 시작한 쌍은 **지금보다 가까워지지 않는 동작만** 허용합니다(속도 항 없음). 0.5 cm 아래로는 어떤 경우에도 안 됩니다.
- 검사가 0.3초를 넘기면 그때까지 확인된 앞부분만 실행하거나 거부합니다.

## 동작 방식

1. **궤적 재구성** (`robot.py`): 액션 22개 → 관절 목표(시뮬 `UnifiedActionsCfg` 와 같은 식) → 컨트롤러별 다점 궤적
   (점마다 위치·속도·가속도, JTC 가 5차 스플라인으로 잇는다). 대시보드가 로봇에 보내는 계산과 같습니다.
2. **촘촘한 샘플**: 이웃 샘플 사이 관절 변화가 0.5°(리프트 3 mm) 이하가 되게 나눕니다. 스플라인은 점 사이에서 튈 수 있습니다.
3. **거리 계산** (pinocchio + coal): 메시를 볼록 껍질로 바꿔 빠르게 재고(껍질 거리 ≤ 실제 거리라 보수적), 허용 거리 근처 쌍만 원래 메시로 다시 잽니다.
4. **빠르게 건너뛰기**: 관절이 Δq 움직일 때 두 부품이 가까워질 수 있는 거리의 상한(관절별 레버)을 미리 계산해,
   그 상한으로도 허용 거리에 닿을 수 없는 구간과 쌍은 재지 않습니다. 건너뛴 구간도 허용 거리 위인 것이 보장됩니다.
5. **검사 제외 쌍**: 바로 붙은 링크, 같은 기구 내부(손목·손가락·손목 카메라 / 몸통·리프트·바퀴 / 머리·ZED, 몸통↔머리),
   관절 한계 안에서는 닿을 수 없는 같은 팔 쌍 31개(`aiw_selfcoll/kin_excluded.json`, `kin_separated.py` 로 만듦).
   ROBOTIS SRDF 의 충돌 제외 목록은 쓰지 않습니다(양팔 사이 쌍까지 빼기 때문).

## 한계 (꼭 읽어 주세요)

- **계산하지 않는 것**: 손에 든 물체, Task C 바코드 스캐너, 선반·탁자 등 주변 물체. 이들의 충돌은 막지 못합니다.
- **제외 쌍의 의미**: "닿을 수 없음"은 거리 > 0 이라는 뜻이지 허용 거리 밖이라는 뜻이 아닙니다. 가장 가까운 쌍(같은 팔 link2↔link4)은 0.3 cm 까지 옵니다.
- **속도 항**: 경로의 60개 시점에서 잰 값으로 사이를 메우는 근사입니다(엄밀한 상한이 아닙니다). 0.02 s 는 실기 측정(손 0.7 m/s 까지 경로 이탈 최대 1.6 cm)에서 정했고, 더 빠른 속도는 측정하지 못했습니다.
- **출발 가정**: 청크를 받을 때 팔이 **멈춰 있다고** 보고 측정 자세에서 출발합니다.
- **모델**: FFW-SG2 follower URDF 의 충돌 형상 기준입니다. 케이블·브래킷처럼 모델에 없는 부분은 여유 두께로만 반영됩니다.

## 설치와 실행

필요: Python 3.10+, `numpy`, `scipy`, `pin`(pinocchio) 4.1+, `coal` 3.0+, 그리고 ROBOTIS FFW-SG2 URDF·메시.

```bash
pip install numpy scipy pin coal pytest
git clone --depth 1 -b jazzy https://github.com/ROBOTIS-GIT/ai_worker.git   # URDF·메시 (Apache-2.0)
export AIW_DESCRIPTION_DIR=$PWD/ai_worker      # ffw_description 의 부모 디렉토리 (ROS 설치본이 있으면 생략 가능)
```

```python
import sys; sys.path.insert(0, "scripts/selfcoll")
import numpy as np
from aiw_selfcoll import POSE_KEYS, SelfCollision, urdf_limits

c = SelfCollision()                                   # 기본 3 cm, 이웃 쌍 2 cm, 0.02 s
lim = urdf_limits(overrides={"head_joint1": (-0.2317, 0.7854)})   # 실기 목 한계 (URDF 상한 0.6951 → 0.7854)
home = {...}                                          # 과제 기준 자세 {POSE_KEYS: 값} — 액션은 이 자세에 대한 상대값
q0 = np.array([home[k] for k in POSE_KEYS])           # 지금 관절 (리셋 직후면 home)
chunk = np.zeros((10, 22))                            # 정책이 낸 청크 (T, 22)
period = 1.0 / (20 * 0.8)                             # 1 / (control_hz × 실행 배율)

g = c.gate_chunk(q0, chunk, period, home, lim)
print(g["verdict"], g["n_exec"], g["full"]["bad_pair"])   # 예: truncate 6 {'pair': (..), 'dist_m': .., 'limit_m': ..}
```

- 관절 벡터 순서는 `POSE_KEYS`(팔 r1–7, 팔 l1–7, 그리퍼 r·l, 목 1·2, 리프트) 19개입니다.
- 연속 청크를 검사할 때는 직전 청크의 마지막 그리퍼 지령을 `grip_cmd={"gripper_l_joint1": .., "gripper_r_joint1": ..}` 로 넘깁니다.
- 별도 프로세스로 돌리려면 `aiw_selfcoll.worker.SelfCollProc` 를 씁니다(카메라·ROS 스레드가 바쁜 프로세스에서 GIL 경쟁을 피함).

## 시험

```bash
cd scripts/selfcoll
python -m pytest -q tests        # URDF 가 없으면 건너뜀
```

`test_passed_paths_hold_under_brute_force` 는 검사기가 통과시킨 경로를 **모든 샘플·모든 쌍의 원래 메시 거리**로 다시 계산해
허용 거리를 깨지 않는지 확인합니다(건너뛰기·거르기의 안전성). 같은 방식으로 무작위 동작 400개(통과 217, 앞부분만 128, 거부 55)와
실기 녹화 청크 240개에서 놓친 위반은 없었습니다.

## 제외 쌍 다시 만들기

URDF 나 관절 한계가 바뀌면 다시 만듭니다(수 분).

```bash
cd scripts/selfcoll && python kin_separated.py      # → aiw_selfcoll/kin_excluded.json
```

## 파일

| 파일 | 내용 |
|---|---|
| `aiw_selfcoll/robot.py` | 관절 순서, 액션 → 관절 목표, 청크 → 다점 궤적, URDF 관절 한계 |
| `aiw_selfcoll/selfcoll.py` | `SelfCollision` (거리 계산, 경로 검사, `gate_chunk` 판정) |
| `aiw_selfcoll/worker.py` | 별도 프로세스 손잡이 `SelfCollProc` |
| `aiw_selfcoll/kin_excluded.json` | 관절 한계상 닿을 수 없는 같은 팔 쌍 목록 |
| `kin_separated.py` | 위 목록 생성기 |
| `tests/test_selfcoll.py` | 시험 |

URDF·메시는 이 저장소에 들어 있지 않습니다. [ROBOTIS-GIT/ai_worker](https://github.com/ROBOTIS-GIT/ai_worker)(Apache-2.0)의 `ffw_description` 을 씁니다.
