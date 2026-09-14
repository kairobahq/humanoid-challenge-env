"""재생기에 **관측 트레이스**를 얹는 패치 — 원본 파일은 건드리지 않는다.

`qr_sweep_replay.py` 를 임시 사본으로 복사한 뒤 문자열 삽입 한 번으로
채점에 필요한 관측을 매 기록 틱마다 jsonl 로 흘린다.

  물체 3종의 자세·속도 / 빔 원점 / 그리퍼 관절 명령·실측 / 파지 상태

**원본 스택 스탬프는 그대로다.** 배포본 `BREAD_V0/` 는 손대지 않는다.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

ANCHOR = """            _rec_act.append(_act)
            _fi = len(_rec_state) - 1"""

INJECT = '''            _rec_act.append(_act)
            _fi = len(_rec_state) - 1
            # ---- 채점 트레이스 (evaluation_draft/scorer/trace_patch.py 삽입) ----
            try:
                import json as _tj
                _tp = os.environ.get("TASKC_SCORE_TRACE", "")
                if _tp:
                    _row = {"f": _fi, "t": float(_fi) * float(_REC_EVERY) / 120.0}
                    _pl = []
                    for _pi in range(len(SCENE["products"])):
                        # InteractiveScene 은 __contains__ 가 없어 `in` 이 인덱스 조회로
                        # 떨어진다(key '0' 오류). 반드시 try 로 잡는다.
                        try:
                            _pe = scene[f"p_{_pi}"]
                        except Exception:
                            continue
                        _pl.append({
                            "slug": SCENE["products"][_pi]["slug"],
                            "pos": [float(v) for v in _pe.data.root_pos_w[0].cpu().numpy()],
                            "quat": [float(v) for v in _pe.data.root_quat_w[0].cpu().numpy()],
                            "vel": [float(v) for v in _pe.data.root_lin_vel_w[0].cpu().numpy()],
                        })
                    _row["products"] = _pl
                    try:
                        _b0t, _bdt = _beam78()
                        _row["beam"] = [float(v) for v in _b0t]
                        _row["bd"] = [float(v) for v in _bdt]
                    except Exception:
                        _row["beam"] = [float(v) for v in B0]
                        _row["bd"] = [float(v) for v in BD]
                    # ---- Sub 2-1 화면 점유율 ----
                    # 스캐너캠 스펙은 재생기 CameraCfg 그대로: 1600x1000, f=31.43, 개구 20.955.
                    # 카메라 자세도 재생기와 같다: eye = b0 + bd*0.03, target = b0 + bd*0.30.
                    _row["cam"] = [1600, 1000, 31.43, 20.955, 0.03, 0.30]
                    _row["slot"] = int(args_cli.slot)
                    try:                     # 대상 상품 로컬 치수(m) -- info.json, 1회만 읽는다
                        _szt = globals()["_TRACE_SZ"]
                    except KeyError:
                        try:
                            _slt = SCENE["products"][args_cli.slot]["slug"]
                            _ift = _tj.load(open(f"{SRC}/{_slt}/info.json"))
                            _szt = [float(v) for v in _ift.get("size", [0, 0, 0])]
                            if max(_szt) > 10:   # mm 로 적힌 경우
                                _szt = [v / 1000.0 for v in _szt]
                        except Exception:
                            _szt = None
                        globals()["_TRACE_SZ"] = _szt
                    _row["tgt_size"] = _szt
                    _row["grip_cmd"] = float(q_g[0, 0])
                    try:
                        _gid = r.find_joints("gripper_l_joint1")[0][0]
                        _row["grip_q"] = float(r.data.joint_pos[0, _gid])
                    except Exception:
                        _row["grip_q"] = None
                    with open(_tp, "a", encoding="utf-8") as _tf:
                        _tf.write(_tj.dumps(_row) + "\\n")
            except Exception as _te:
                print(f"[TRACE] 실패: {_te}", flush=True)
            # ---- 트레이스 끝 ----'''


REC_ANCHOR = '        _REC_DIR = f"{ROOT}/out/pi05/episodes_in/{_slug0}_{args_cli.seed}"'
REC_INJECT = '''        # 트레이스 사본은 **에피소드 디렉터리를 건드리지 않는다**.
        # 훅이 `if _REC:` 안에 있어 TASKC_RECORD=1 이 필요한데, 그대로 두면
        # 확보해 둔 GT 에피소드를 덮어쓴다.
        _REC_DIR = f"{ROOT}/out/trace_scratch/{_slug0}_{args_cli.seed}"'''

def make_traced_copy(src: str, dst: str) -> str:
    text = pathlib.Path(src).read_text(encoding="utf-8")
    n = text.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"앵커가 {n}회 -- 재생기 구조가 바뀌었다. 패치를 다시 맞춰야 한다.")
    text = text.replace(ANCHOR, INJECT, 1)
    if text.count(REC_ANCHOR) != 1:
        raise SystemExit("기록 디렉터리 앵커 불일치 -- 에피소드 덮어쓰기를 막을 수 없다")
    text = text.replace(REC_ANCHOR, REC_INJECT, 1)
    pathlib.Path(dst).write_text(text, encoding="utf-8")
    return dst


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "taskC/v4/qr_sweep_replay.py"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/qr_sweep_replay_traced.py"
    if not pathlib.Path(src).is_file():
        # 수집 파이프라인 쪽 도구다 -- 배포본에는 qr_sweep_replay.py 가 없다. 참가자는 task_c_replay.py --trace 를 쓴다.
        raise SystemExit("사용법: trace_patch.py <qr_sweep_replay.py 경로> [출력 사본]\n"
                         f"원본이 없습니다: {src}  (이 도구는 수집 파이프라인용입니다. "
                         "재생 관측은 task_c_replay.py --trace DIR 로 남기십시오)")
    print("패치 사본:", make_traced_copy(src, dst))
    shutil.copystat(src, dst)
