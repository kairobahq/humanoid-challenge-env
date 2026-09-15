# Copyright 2026.
#
# 허깅페이스에 공개된 학습 데이터(LeRobot v2.1)의 한 편을 재생기가 읽는 폴더 형태로 펼친다.
#
#     https://huggingface.co/datasets/SSU-RealityLab/2026CS-Store-Challenge
#
# 재생기는 `demos_gt/` · `demos/` 와 같은 모양의 폴더만 읽는다(`actions.npy` · `joints.npy` ·
# `timestamps.npy` · `phases.json` · `meta.json` · 장면 JSON). 내려받은 데이터셋은 편마다
# parquet 한 장이라 모양이 다르므로 여기서 옮겨 담는다.
#
# **장면(상품이 계산대 어디에 놓였나)은 데이터셋에 없다.** 과제 A 가 매장 12판을
# `taskA/stores/` 에 싣고 있듯, 과제 C 도 1,089 편의 장면을 `taskC/scenes/<시드>.json` 으로
# 저장소에 싣는다. 데이터셋 쪽 `meta/taskC_episodes.jsonl` 이 편마다 `seed` 를 주므로
# 그 값으로 짝을 찾는다.
#
# 쓰는 법 (재생기가 알아서 부르므로 보통은 직접 부를 일이 없다):
#
#     python -m taskC.taskC_lerobot <데이터셋경로> 792            # 펼치고 경로를 찍는다
#     python scripts/taskC/taskC_lerobot.py <데이터셋경로> 792 --out /tmp/ep792
#
# parquet 을 읽어야 하므로 `pyarrow` 가 필요하다. 데이터셋을 내려받았다면 이미 깔려 있다
# (`lerobot` · `datasets` 둘 다 의존한다). 시뮬레이터 쪽 파이썬에 없으면:
#
#     ${ISAACLAB_PATH}/_isaac_sim/python.sh -m pip install pyarrow

import json
import os

import numpy as np

__all__ = ["materialize", "episode_record", "scene_path", "SCENES_DIR"]

_HERE = os.path.dirname(os.path.abspath(__file__))
SCENES_DIR = os.path.join(_HERE, "scenes")

# 22 열 규약. 데이터셋의 `action` · `observation.state` 열 이름과 같은 차례다.
_N_COLS = 22


def _need_pyarrow():
    try:
        import pyarrow.parquet as pq
        return pq
    except ImportError:
        raise SystemExit(
            "parquet 을 읽으려면 pyarrow 가 필요하다. 다음 한 줄이면 된다:\n"
            "    ${ISAACLAB_PATH}/_isaac_sim/python.sh -m pip install pyarrow")


def _meta_dir(root):
    d = os.path.join(root, "meta")
    if not os.path.isdir(d):
        raise SystemExit("데이터셋 경로가 아니다 (meta/ 가 없다): %s" % root)
    return d


def episode_record(root, episode_index):
    """`meta/taskC_episodes.jsonl` 에서 한 편의 기록을 찾는다."""
    f = os.path.join(_meta_dir(root), "taskC_episodes.jsonl")
    if not os.path.isfile(f):
        raise SystemExit("meta/taskC_episodes.jsonl 이 없다: %s" % root)
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("episode_index") == episode_index:
                return d
    raise SystemExit("%d 번 편이 목록에 없다: %s" % (episode_index, f))


def _phase_names(root):
    f = os.path.join(_meta_dir(root), "taskC_products.json")
    if os.path.isfile(f):
        d = json.load(open(f, encoding="utf-8"))
        names = d.get("phase_index") or {}
        return {int(k): v for k, v in names.items()}
    return {}


def _parquet_path(root, episode_index):
    info = json.load(open(os.path.join(_meta_dir(root), "info.json"), encoding="utf-8"))
    tmpl = info.get("data_path") or "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"
    chunk = episode_index // int(info.get("chunks_size", 1000))
    p = os.path.join(root, tmpl.format(episode_chunk=chunk, episode_index=episode_index))
    if not os.path.isfile(p):
        raise SystemExit("편 파일이 없다: %s" % p)
    return p


def scene_path(seed, scenes_dir=None):
    """시드로 장면 JSON 을 찾는다. 저장소에 실린 1,089 편을 먼저 본다."""
    p = os.path.join(scenes_dir or SCENES_DIR, "%d.json" % seed)
    return p if os.path.isfile(p) else None


def _column(table, name):
    """parquet 의 한 열을 (프레임, 차원) 배열로. 없으면 None."""
    if name not in table.column_names:
        return None
    col = table.column(name).to_pylist()
    a = np.asarray(col)
    return a


def materialize(root, episode_index, out_dir=None, scenes_dir=None, log=print):
    """데이터셋의 한 편을 재생기가 읽는 폴더로 펼치고 그 경로를 돌려준다.

    이미 펼쳐져 있고 길이가 같으면 다시 만들지 않는다.
    """
    rec = episode_record(root, episode_index)
    seed = int(rec["seed"])
    n_want = int(rec.get("length") or 0)
    out_dir = out_dir or os.path.join(_HERE, ".lerobot_cache", "ep%06d" % episode_index)

    scene = scene_path(seed, scenes_dir)
    if scene is None:
        raise SystemExit(
            "시드 %d 의 장면 JSON 이 없다. 저장소의 %s 를 확인하라 -- 데이터셋에는 장면이 들어 "
            "있지 않고, 과제 A 의 매장처럼 저장소가 싣는다." % (seed, scenes_dir or SCENES_DIR))

    done = os.path.join(out_dir, "actions.npy")
    if os.path.isfile(done) and (not n_want or len(np.load(done)) == n_want):
        return out_dir

    pq = _need_pyarrow()
    table = pq.read_table(_parquet_path(root, episode_index),
                          columns=[c for c in ("action", "observation.state", "timestamp",
                                               "phase_index", "frame_index")])
    act = _column(table, "action")
    st = _column(table, "observation.state")
    if act is None:
        raise SystemExit("action 열이 없다: %s" % root)
    act = np.asarray(act, dtype=np.float32)
    st = np.asarray(st if st is not None else act, dtype=np.float32)
    if act.ndim != 2 or act.shape[1] != _N_COLS:
        raise SystemExit("action 이 (프레임, %d) 여야 하는데 %s 다" % (_N_COLS, act.shape))

    ts = _column(table, "timestamp")
    ts = np.asarray(ts, dtype=np.float64).reshape(-1) if ts is not None \
        else np.arange(len(act), dtype=np.float64) / 30.0

    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "actions.npy"), act)
    np.save(os.path.join(out_dir, "joints.npy"), st)
    np.save(os.path.join(out_dir, "timestamps.npy"), ts)

    # 국면 -- `phase_index` 가 바뀌는 프레임이 국면의 시작이다.
    ph = _column(table, "phase_index")
    if ph is not None:
        ph = np.asarray(ph, dtype=np.int64).reshape(-1)
        names = _phase_names(root)
        marks = [0] + [i for i in range(1, len(ph)) if ph[i] != ph[i - 1]]
        phases = [{"name": names.get(int(ph[i]), str(int(ph[i]))), "start_frame": int(i)} for i in marks]
        json.dump({"phases": phases, "n_frames": int(len(act))},
                  open(os.path.join(out_dir, "phases.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    with open(scene, encoding="utf-8") as fh:
        scene_doc = json.load(fh)
    json.dump(scene_doc, open(os.path.join(out_dir, "taskC_qr_scene_%d.json" % seed), "w",
                              encoding="utf-8"), ensure_ascii=False, indent=1)

    meta = {"slug": rec.get("product"), "seed": seed, "grade": rec.get("grade"),
            "product_name": rec.get("product_name_ko"), "instruction": rec.get("instruction_ko"),
            "subtasks": rec.get("subtasks_ko"), "source_seed": seed, "record_hz": 30,
            "n_frames": int(len(act)), "seconds": round(float(len(act)) / 30.0, 1),
            "episode_index": int(episode_index), "dataset": os.path.abspath(root),
            "note": "허깅페이스 학습 데이터에서 펼친 판. 장면은 저장소의 taskC/scenes/ 에서 왔다."}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if log:
        log("[LEROBOT] ep %d (%s, 시드 %d) %d 프레임 -> %s"
            % (episode_index, rec.get("product"), seed, len(act), out_dir))
    return out_dir


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="허깅페이스 학습 데이터 한 편을 재생기가 읽는 폴더로 펼친다.")
    ap.add_argument("root", help="내려받은 데이터셋 경로 (meta/ 와 data/ 가 있는 곳)")
    ap.add_argument("episode", type=int, help="편 번호 (meta/taskC_episodes.jsonl 의 episode_index)")
    ap.add_argument("--out", default=None, help="펼칠 곳 (기본: taskC/.lerobot_cache/ep<번호>)")
    ap.add_argument("--scenes", default=None, help="장면 폴더 (기본: taskC/scenes)")
    a = ap.parse_args()
    print(materialize(a.root, a.episode, a.out, a.scenes))


if __name__ == "__main__":
    _cli()
