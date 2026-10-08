"""--zed-depth 로 남긴 판들(<이름>/summary.json 이 있는 폴더)을 모아 시뮬 depth 와 ZED depth 의 차이를 한눈에 보인다.
과제 A · B · C 를 섞어도 된다.

남기는 것 (--out, 기본은 판들이 있는 폴더):
    summary_all.json            판마다 · 전체의 거리 구간별 |ZED - 시뮬| (중앙값 · 90 % · 20 mm · 50 mm 넘는 비율 · ZED 값 없음)
    summary_by_distance.png     거리 구간별 |ZED - 시뮬| 중앙값과 20 mm 넘는 비율 (판마다 가는 선, 전체 굵은 선)
    examples.png                판마다 한 장씩: head_l · 시뮬 depth · ZED depth · ZED - 시뮬

    python zed_summary.py /workspace/user/zed_depth
"""
import argparse
import glob
import json
import os

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BINS = ["0-600", "600-900", "900-1200", "1200-2000", "2000-3000"]


def colour_depth(d, lo=400, hi=2000):
    x = ((np.clip(d.astype(np.float32), lo, hi) - lo) / (hi - lo) * 255).astype(np.uint8)
    c = cv2.applyColorMap(x, cv2.COLORMAP_TURBO)
    c[d == 0] = 0
    return c


def colour_diff(d_sim, d_zed, lim=50.0):
    t = np.clip((d_zed.astype(np.float32) - d_sim.astype(np.float32)) / lim, -1.0, 1.0)
    c = (np.dstack([np.where(t < 0, 1.0, 1.0 - t), 1.0 - np.abs(t), np.where(t > 0, 1.0, 1.0 + t)]) * 255).astype(np.uint8)
    c[(d_sim == 0) | (d_zed == 0)] = 0
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default="")
    ap.add_argument("--at", type=float, default=0.6, help="예시 그림을 판의 몇 할 지점에서 고를까")
    a = ap.parse_args()
    out = a.out or a.root
    demos = sorted(d for d in glob.glob(os.path.join(a.root, "*")) if os.path.exists(os.path.join(d, "summary.json")))
    if not demos:
        raise SystemExit(f"summary.json 이 있는 판이 없다: {a.root}")
    S = {os.path.basename(d): json.load(open(os.path.join(d, "summary.json"))) for d in demos}
    json.dump(S, open(os.path.join(out, "summary_all.json"), "w"), indent=1, ensure_ascii=False)

    print(f"{'판':24s} {'프레임':>6s} {'ZED 실패':>8s} {'3 m 안 |차| 중앙':>14s} {'90 %':>6s} {'>20 mm':>7s} {'>50 mm':>7s}")
    for k, s in S.items():
        w = s["within_3m"] or {}
        print(f"{k:24s} {s['frames']:6d} {s['zed_failed']:8d} {str(w.get('abs_median_mm')) + ' mm':>14s} "
              f"{w.get('abs_p90_mm', '-'):>6} {100 * w.get('over20', 0):6.1f}% {100 * w.get('over50', 0):6.1f}%")
    print("\n거리 구간(시뮬 depth)별 -- 판 전체를 픽셀 수로 합친 것은 summary_all.json 에 판마다, 아래는 판들의 중앙")
    for b in BINS:
        vals = [s["by_distance_mm"].get(b, {}) for s in S.values()]
        med = [v.get("abs_median_mm") for v in vals if v.get("abs_median_mm") is not None]
        o20 = [v.get("over20") for v in vals if v.get("over20") is not None]
        holes = [v.get("zed_holes") for v in vals if v.get("zed_holes") is not None]
        if med:
            print(f"  {b:>9s} mm: |ZED-시뮬| 중앙값 {np.median(med):5.1f} mm · 20 mm 넘게 {100 * np.median(o20):5.1f} % · "
                  f"ZED 값 없음 {100 * np.median(holes):4.1f} %  (판 {len(med)})")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    x = np.arange(len(BINS))
    for k, s in S.items():
        v = [s["by_distance_mm"].get(b, {}) for b in BINS]
        ax[0].plot(x, [e.get("abs_median_mm", np.nan) for e in v], "-o", lw=1, ms=3, alpha=0.6, label=k)
        ax[1].plot(x, [100 * e.get("over20", np.nan) for e in v], "-o", lw=1, ms=3, alpha=0.6, label=k)
    for i, (title, unit) in enumerate((("|ZED - sim| median", "mm"), ("pixels off by > 20 mm", "%"))):
        ax[i].set_xticks(x, [f"{b}" for b in BINS], fontsize=8)
        ax[i].set_xlabel("sim depth (mm)")
        ax[i].set_ylabel(unit)
        ax[i].set_title(title)
        ax[i].grid(alpha=0.3)
    ax[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "summary_by_distance.png"), dpi=120)

    rows = []
    for d in demos:
        frames = sorted(glob.glob(os.path.join(d, "depth_zed", "*.png")))
        if not frames:
            continue
        f = os.path.basename(frames[int(a.at * (len(frames) - 1))])[:-4]
        left = cv2.imread(os.path.join(d, "head_l", f + ".jpg"))
        ds = cv2.imread(os.path.join(d, "depth_sim", f + ".png"), -1)
        dz = cv2.imread(os.path.join(d, "depth_zed", f + ".png"), -1)
        row = np.hstack([left, colour_depth(ds), colour_depth(dz), colour_diff(ds, dz)])
        cv2.putText(row, f"{os.path.basename(d)} frame {int(f)}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        rows.append(cv2.resize(row, (row.shape[1] // 2, row.shape[0] // 2), interpolation=cv2.INTER_AREA))
    head = np.zeros((24, rows[0].shape[1], 3), np.uint8)
    for i, t in enumerate(["head_l", "sim depth 400-2000 mm", "ZED depth 400-2000 mm", "ZED - sim +-50 mm (blue nearer, red farther)"]):
        cv2.putText(head, t, (6 + i * rows[0].shape[1] // 4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.imwrite(os.path.join(out, "examples.png"), np.vstack([head] + rows))
    print(f"\n남김: {out}/summary_all.json · summary_by_distance.png · examples.png")


if __name__ == "__main__":
    main()
