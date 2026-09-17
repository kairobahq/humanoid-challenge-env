# Copyright 2026.
#
# 재생 중의 관측을 채점기가 읽는 형식으로 흘린다.
#
# 과제 B 가 `task_b_episode.py` 로 state npz 를 쓰고 `taskb_score.py` 가 그것을 읽듯,
# 과제 C 는 `task_c_replay.py --trace` 가 이 모듈로 jsonl 을 쓰고
# `score_from_trace.py` 가 그것을 읽는다. 채점기는 Isaac 을 모른다.
#
# 한 줄에 담기는 것:
#
#     t           재생 시각(초)
#     slot        지금 다루는 슬롯 (-1 이면 아직 없음)
#     products[]  슬러그 · 자세(pos, quat wxyz) · 속도
#     beam, bd    빔 원점과 방향
#     grip_cmd    왼 그리퍼 명령값 (기록에서 온 값)
#     grip_q      같은 관절 실측값
#     cam         스캐너캠 스펙 [W, H, focal_mm, aperture_mm, d_eye, d_tgt]
#     tgt_size    대상 상품의 전체 치수 (he x 2)
#
# 좌표는 전부 **환경 원점 기준**이다. 채점기가 상판 높이와 띠를 장면 파일에서 재서 쓰므로
# 그 둘과 같은 기준이어야 한다.

import json
import os

__all__ = ["TraceWriter", "SCANNER_CAM"]

# 스캐너캠 스펙. 채점기의 화면 점유율(Sub 2-1)이 이 값으로 카메라를 해석적으로 재현한다.
# V4-250 과 같은 배치다 -- 눈은 빔 출발선에서 3 cm, 겨눔점은 30 cm.
SCANNER_CAM = [1600, 1000, 31.43, 27.2415, 0.03, 0.30]   # 2026-09-18 화각 30% 확대 (qr_decode.SCAN_CAM 과 같은 가로 조리개)


class TraceWriter:
    """jsonl 한 줄 = 한 프레임. 닫을 때 장면·판독 요약을 함께 남긴다."""

    def __init__(self, out_dir, scene, products, log=None):
        os.makedirs(out_dir, exist_ok=True)
        self.dir = out_dir
        self.f = open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8")
        self.scene = scene
        self.products = products
        self.decode = []
        self._log = log or (lambda m: None)
        self._n = 0
        self.q_free_close = None   # 빈손 닫힘 위치 (재생기가 재서 넣는다)
        self.qr = None             # 이미지 판독기 요약 (판독 창·냉각·시도 횟수)
        # 채점기는 장면 파일에서 상판 높이와 띠를 잰다. 그대로 옆에 둔다.
        with open(os.path.join(out_dir, "scene.json"), "w", encoding="utf-8") as fh:
            json.dump(scene, fh, ensure_ascii=False)

    def tick(self, t, slot, poses, vels, beam0, beam_dir, grip_cmd, grip_q):
        """poses[i] = (pos3, quat_wxyz4), vels[i] = 선속도 3."""
        he = self.products[slot]["he"] if 0 <= slot < len(self.products) else None
        row = {
            "t": round(float(t), 4),
            "slot": int(slot),
            "products": [
                {"slug": self.products[i]["slug"],
                 "pos": [round(float(v), 6) for v in poses[i][0]],
                 "quat": [round(float(v), 6) for v in poses[i][1]],
                 "vel": [round(float(v), 6) for v in vels[i]]}
                for i in range(len(self.products))],
            "beam": [round(float(v), 6) for v in beam0],
            "bd": [round(float(v), 6) for v in beam_dir],
            "grip_cmd": round(float(grip_cmd), 6),
            "grip_q": round(float(grip_q), 6),
            "cam": SCANNER_CAM,
        }
        if he is not None:
            row["tgt_size"] = [round(float(v) * 2.0, 6) for v in he]
        self.f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._n += 1
        if self._n % 200 == 0:
            self.f.flush()

    def note_decode(self, slot, slug, frame, lat_mm, dist_mm, text=None, by="image"):
        """판독이 성립한 순간을 남긴다. 채점기는 이것을 판독 성공의 근거로 쓴다.

        `by="image"` 는 스캐너캠 그림을 디코드해 그 상품의 코드가 나왔다는 뜻이다. 다른 값은 점수가 되지 않는다.
        """
        self.decode.append({"ok": True, "slot": int(slot), "slug": slug,
                            "frame": int(frame), "lat_mm": round(float(lat_mm), 2),
                            "dist_mm": round(float(dist_mm), 1),
                            "by": by, "text": text})

    def close(self, grade=None):
        self.f.close()
        with open(os.path.join(self.dir, "decode.json"), "w", encoding="utf-8") as fh:
            json.dump({"decode": self.decode, "grade": grade,
                       "q_free_close": self.q_free_close, "qr": self.qr},
                      fh, ensure_ascii=False, indent=1)
        self._log("[TRACE] %d 프레임 · 판독 %d건 -> %s"
                  % (self._n, len(self.decode), self.dir))
