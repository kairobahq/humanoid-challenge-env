# Copyright 2025.
#
# seed 하나가 장면 하나를 정하는 **규칙**. 여기 있는 것이 그 전부다.
#
# 한 장면에서 seed 가 정하는 것은 셋이다.
#
#   선반씨앗    맨 위 판 3 열에 무엇이 서 있고, 그 중 **어느 한 열의 앞자리가 비는지**
#   크레이트씨앗 비는 자리의 상품이 파란 크레이트 안 어디에 놓이는지
#   배경씨앗    주변에 어느 매장 기물이 몇 개 어디에 서 있는지
#
# **빈 자리와 크레이트는 따로 뽑지 않는다.** 선반씨앗이 어느 열을 비울지 정하고, 그 열의
# 상품이 그대로 크레이트에 들어간다 -- 로봇이 채워 넣어야 하는 것이 바로 그 상품이기 때문에
# 둘은 한 뽑기의 두 면이다. 따로 뽑으면 "크레이트에 든 것과 빈 칸이 다른 상품" 이라는, 과제가
# 성립하지 않는 장면이 나온다.
#
# **자리는 안 바뀌고 물건만 바뀐다.** 선반·책상·크레이트·로봇의 좌표는 seed 와 무관하고
# (`taskD_layout.py`), 바뀌는 것은 그 위에 선 물건과 주변 기물이다. 그래서 충돌 판정이 보는
# 발자국은 seed 와 무관하고, 정책이 보는 그림만 매번 달라진다. 과제 A 가 같은 규칙을 쓴다.
#
# 왜 `random` 을 안 쓰나
#   `random.Random(seed)` 는 파이썬 판이 바뀌면 다른 수열을 낼 수 있고, 다른 언어에서는
#   재현할 방법이 아예 없다. 여기서는 md5 앞 8 자리를 정수로 읽는다 -- 파이썬이 없어도,
#   손으로도, 같은 값이 나온다. `scripts/taskA/taskA_scene_seed.py` 와 같은 방식이다.
#
#       shelf_seed   = int(md5("taskD-eval-shelf|<seed>")[:8],   16) % 999999 + 1
#       crate_seed   = int(md5("taskD-eval-crate|<seed>")[:8],   16) % 999999 + 1
#       clutter_seed = int(md5("taskD-eval-clutter|<seed>")[:8], 16) % 999999 + 1
#
#   **파생된 씨앗을 받은 뒤, 모듈 안에서 `random.Random(그 씨앗)` 을 쓰는 것은 괜찮다.**
#   과제 A 도 그렇게 한다 (`taskA_seats.py:178` 이 파생 씨앗으로 의자 각도를 뽑는다).
#   md5 로 막는 것은 **참가자와 주최 측이 합의해야 하는 최상위 파생**이고, 그 아래 한 모듈
#   안에서 한 번 쓰이는 수열은 합의 대상이 아니다. 이 구분을 흐리면 과제 B 에서 물려받은
#   진열 규칙(칸 간격·잔떨림·진열 각도)을 전부 다시 구현해야 하고, 그것은 검증된 동작을
#   그릇 바꾸는 작업에서 함께 바꾸는 일이 된다.
#
# **이 값을 바꾸면 안 된다.** 바꾸면 같은 seed 가 주최 측과 참가자에게 다른 장면이 되고,
# 그것은 조용히 어긋난다 -- 두 장면 다 정상으로 열리고 로봇도 잘 움직인다.
#
# isaaclab 도 numpy 도 pxr 도 안 쓴다. `task_d_demo.py --check` 가 Isaac Sim 없이 1 초에
# 도는 것은 이 파일과 `taskD_layout.py` 가 순수 파이썬이기 때문이다.
#
# 혼자 돌려 볼 수 있다:
#     python3 scripts/taskD/taskD_scene_seed.py --seed 0 1 2 1000
#     python3 scripts/taskD/taskD_scene_seed.py --seed 1000 --json

import hashlib
import json

# 네임스페이스. 과제마다 달라야 한다 -- 같으면 과제 A 의 seed 1000 과 태스크 D 의 seed 1000 이
# 같은 수열을 받고, 두 과제의 "무작위" 가 서로 상관을 갖는다.
NS = "taskD-eval"

# 뽑는 스트림. 하나를 더 쓰려면 여기 적고 `spec()` 에 넣는다 -- 이름만으로 독립이다.
STREAMS = ("shelf", "crate", "clutter")


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _draw(seed, what):
    """스트림 씨앗 하나. 1 ~ 999999.

    범위는 과제 A 와 같다 -- 그쪽 원본이 `rng.randrange(1, 10**6)` 로 뽑는다.
    """
    return int(_md5("%s-%s|%d" % (NS, what, int(seed)))[:8], 16) % 999999 + 1


def _unit(seed, what):
    """0 이상 1 미만의 수 하나. `_draw()` 와 같은 md5 방식."""
    return int(_md5("%s-%s|%d" % (NS, what, int(seed)))[:8], 16) / float(1 << 32)


def spec(seed):
    """seed -> 장면 하나. **이 함수가 규칙의 전부다.**"""
    seed = int(seed)
    if seed < 0:
        raise ValueError("seed 는 0 이상이어야 한다 (받은 값 %d)" % seed)
    out = {"seed": seed}
    for name in STREAMS:
        out["%s_seed" % name] = _draw(seed, name)
    out["rule"] = ("%s_seed = md5(\"%s-<스트림>|<seed>\")[:8] %% 999999 + 1, "
                   "스트림 %s" % ("/".join(STREAMS), NS, ", ".join(STREAMS)))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="seed 가 어떤 장면이 되는지 보여준다. Isaac Sim 을 안 띄운다.")
    ap.add_argument("--seed", type=int, nargs="*", default=[0, 1, 2, 1000], help="볼 seed 들")
    ap.add_argument("--json", action="store_true", help="JSON 으로")
    a = ap.parse_args()

    out = [spec(s) for s in a.seed]
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print("seed         선반씨앗   크레이트씨앗   배경씨앗")
    for s in out:
        print("%-10d  %8d   %10d   %8d"
              % (s["seed"], s["shelf_seed"], s["crate_seed"], s["clutter_seed"]))


if __name__ == "__main__":
    main()
