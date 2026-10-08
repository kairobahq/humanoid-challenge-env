"""과제 D: zed_depth_server.py 에 머리 두 눈 그림을 보내고 depth 를 받는 클라이언트 (표준 라이브러리 + numpy).

    from zed_depth_client import ZedDepthClient
    zc = ZedDepthClient("127.0.0.1", 7300)
    depth_mm, rect_left, info = zc.depth(left_rgb, right_rgb)
    # depth_mm (376, 672) uint16 mm (0 = 값 없음) · rect_left SDK 가 정류한 왼쪽 RGB (depth 가 정합된 그림)
    # info {"ok", "rx_err", "tries", "ms", "K_rect": [fx, fy, cx, cy], "baseline_mm"}
"""
import json
from multiprocessing.connection import Client

import numpy as np

AUTHKEY = b"taskd-zed-depth"


class ZedDepthClient:
    def __init__(self, host="127.0.0.1", port=7300):
        self.conn = Client((host, port), authkey=AUTHKEY)

    def depth(self, left_rgb, right_rgb):
        left = np.ascontiguousarray(left_rgb, np.uint8)
        right = np.ascontiguousarray(right_rgb, np.uint8)
        h, w = left.shape[:2]
        self.conn.send_bytes(json.dumps({"w": w, "h": h}).encode())
        self.conn.send_bytes(left.tobytes())
        self.conn.send_bytes(right.tobytes())
        info = json.loads(self.conn.recv_bytes())
        d = np.frombuffer(self.conn.recv_bytes(), np.uint16).reshape(h, w)
        rect = np.frombuffer(self.conn.recv_bytes(), np.uint8).reshape(h, w, 3)
        return d, rect, info

    def close(self):
        self.conn.close()
