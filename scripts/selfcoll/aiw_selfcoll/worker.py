"""검사기를 **별도 프로세스**로 돌리는 손잡이 (SelfCollProc).

왜: 카메라·ROS 콜백 스레드가 바쁜 파이썬 프로세스 안에서 돌리면 GIL 을 다퉈 느려진다 (Jetson Orin 실측, 같은 306 청크:
같은 프로세스 중앙값 159 ms, 따로 돌리면 27 ms). 또 OpenBLAS 가 작은 행렬에도 스레드를 여러 개 띄워 2배 느렸다 →
자식은 OPENBLAS_NUM_THREADS=1 로 시작한다 (numpy 를 부르기 전에 정해야 하므로 환경 변수로).

통신: socketpair 위의 multiprocessing Connection (pickle).
  ("cfg", padding, close_padding, speed_k, budget_s) → 응답 없음
  ("gate", q0, A, period, home, limits, grip) → ("ok", 요약 dict) | ("err", 사유)
"""
import os
import socket
import subprocess
import sys
import threading
from multiprocessing.connection import Connection
from pathlib import Path


def _summary(g):
    full = g["full"]
    return {"verdict": g["verdict"], "reason": g["reason"], "n_exec": int(g["n_exec"]),
            "full": {k: full.get(k) for k in ("bad_pair", "pair", "min_dist_m")}}


def main():
    conn = Connection(int(sys.argv[1]))
    try:
        from .selfcoll import SelfCollision
        c = SelfCollision()
    except Exception as e:  # noqa: BLE001 — 부모가 사유를 받는다
        conn.send(("err", f"{type(e).__name__}: {e}"))
        return
    conn.send(("ready", len(c.pairs)))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return                     # 부모가 끝났다
        if msg[0] == "cfg":
            _, c.padding, c.close_padding, c.SPEED_K, c.BUDGET_S = msg
        elif msg[0] == "gate":
            _, q0, A, period, home, limits, grip = msg
            try:
                conn.send(("ok", _summary(c.gate_chunk(q0, A, period, home, limits, grip))))
            except Exception as e:  # noqa: BLE001
                conn.send(("err", f"{type(e).__name__}: {e}"))


class SelfCollProc:
    """부모 쪽 손잡이. start() 는 검사기 준비(수 초)까지 막는다 — 필요하면 백그라운드 스레드에서 부른다."""

    def __init__(self):
        self.proc, self.conn, self.n_pairs = None, None, None
        self.lock = threading.Lock()

    def start(self, timeout=120.0):
        a, b = socket.socketpair()
        root = str(Path(__file__).resolve().parents[1])   # aiw_selfcoll 의 부모 — 자식이 패키지를 찾게
        env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
               "PYTHONPATH": os.pathsep.join(filter(None, [root, os.environ.get("PYTHONPATH")]))}
        self.proc = subprocess.Popen([sys.executable, "-m", "aiw_selfcoll.worker", str(b.fileno())],
                                     pass_fds=(b.fileno(),), env=env)
        b.close()
        self.conn = Connection(a.detach())
        if not self.conn.poll(timeout):
            self.close()
            raise TimeoutError(f"검사기 프로세스가 {timeout:g} s 안에 준비되지 않음")
        kind, val = self.conn.recv()
        if kind != "ready":
            self.close()
            raise RuntimeError(val)
        self.n_pairs = val

    def configure(self, padding, close_padding, speed_k, budget_s):
        with self.lock:
            self.conn.send(("cfg", float(padding), float(close_padding), float(speed_k), float(budget_s)))

    def gate(self, q0, A, period, home, limits, grip, wait_s):
        """→ gate_chunk 요약 dict. 프로세스가 죽었거나 wait_s 안에 답이 없으면 RuntimeError (부르는 쪽은 거부로 처리)."""
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError("검사기 프로세스가 없다")
            self.conn.send(("gate", q0, A, period, home, limits, grip))
            if not self.conn.poll(wait_s):
                self.close()           # 늦은 답이 다음 요청에 섞이지 않게 버린다
                raise RuntimeError(f"검사기 응답 없음 ({wait_s:g} s)")
            kind, val = self.conn.recv()
        if kind != "ok":
            raise RuntimeError(val)
        return val

    def close(self):
        if self.conn is not None:
            self.conn.close()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


if __name__ == "__main__":
    main()
