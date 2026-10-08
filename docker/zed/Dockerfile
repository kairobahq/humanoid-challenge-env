# 실기 같은 머리 depth 를 계산하는 ZED SDK 컨테이너 -- scripts/zed_depth/zed_depth_server.py 를 돌린다 (docs/zed_depth.md).
# Stereolabs 공식 이미지(ZED SDK 5.5, CUDA 12.8 -- NVIDIA 드라이버 570 이상) 위에 numpy · OpenCV 와 pyzed(ZED SDK 의
# 파이썬 바인딩)만 더한다. pyzed 는 Stereolabs 의 설치 스크립트가 SDK 판에 맞는 것을 받아 깐다.
FROM stereolabs/zed:5.5.0-devel-cuda12.8-ubuntu24.04
RUN pip3 install --break-system-packages --no-cache-dir numpy opencv-python-headless \
 && cd /tmp && python3 /usr/local/zed/get_python_api.py --force && rm -f /tmp/*.whl \
 && python3 -m pip show pyzed | head -2
# pyzed 를 불러오는 시험은 여기서 못 한다 -- 빌드 때는 GPU 드라이버(libcuda.so.1)가 없다. 컨테이너를 띄운 뒤 서버가 연다.
