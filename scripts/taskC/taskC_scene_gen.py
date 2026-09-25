# Copyright 2026.
#
# 과제 C 씬 생성기 고르기 (2026-09-26 추가). 생성기는 두 벌이다.
#
#   qr_right   `taskC_deal` + `taskC_check`             QR 면이 세계 -Y(정 오른쪽)를 본다 (종전 그대로)
#   rand       `taskC_deal_rand` + `taskC_check_rand`   QR 면이 무작위 방위 (360 도). 바닥 닿는 면과
#                                                       자리 규칙(띠·8 cm·그리퍼)은 같다
#
# 평가는 3 회차다. **앞 두 회차는 qr_right, 마지막 회차는 rand** 가 기본이다 (`auto`).
# 회차는 시드로 정한다: 회차 = 시드 % 3 -> 0·1 은 qr_right, 2 는 rand. 평가 표본 시드 0·1·2 가
# 곧 1·2·3 회차다. 같은 시드는 언제나 같은 생성기 -> 같은 장면이다.
#
# 고르는 곳은 이 파일 하나다. 쓰는 쪽은
#
#     from taskC import taskC_scene_gen as SG
#     kind = SG.resolve(mode, seed)        # mode: "auto" | "qr_right" | "rand"
#     D, K = SG.modules(kind)              # D.deal / D.pick_products / D.Infeasible, K.check_settled ...
#
# mode 를 안 주면 환경변수 `TASKC_SCENE_GEN` 을, 그것도 없으면 "auto" 를 쓴다.

import os

MODES = ("auto", "qr_right", "rand")
KINDS = ("qr_right", "rand")
EPISODES = 3            # 평가 회차 수
RAND_EPISODE = 2        # 0 부터 센 회차 번호 -- 마지막(3 번째) 회차가 rand
ENV = "TASKC_SCENE_GEN"


def default_mode():
    """플래그가 없을 때의 모드: 환경변수 `TASKC_SCENE_GEN`, 없으면 "auto"."""
    return os.environ.get(ENV, "auto").strip() or "auto"


def episode_of(seed):
    """시드의 회차 (0 부터). 평가 표본 시드 0·1·2 -> 0·1·2."""
    return int(seed) % EPISODES


def resolve(mode, seed):
    """모드와 시드로 실제 생성기 이름("qr_right" | "rand")을 정한다."""
    mode = default_mode() if mode is None else str(mode)
    if mode not in MODES:
        raise ValueError(f"모르는 씬 생성기 모드: {mode!r} (가능: {', '.join(MODES)})")
    if mode == "auto":
        return "rand" if episode_of(seed) == RAND_EPISODE else "qr_right"
    return mode


def modules(kind):
    """(딜 모듈, 정착 검사 모듈). 두 쌍은 이름·인자가 같아 그대로 바꿔 끼울 수 있다."""
    if kind == "qr_right":
        from . import taskC_check as K
        from . import taskC_deal as D
    elif kind == "rand":
        from . import taskC_check_rand as K
        from . import taskC_deal_rand as D
    else:
        raise ValueError(f"모르는 씬 생성기: {kind!r} (가능: {', '.join(KINDS)})")
    return D, K
