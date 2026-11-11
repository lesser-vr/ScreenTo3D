ScreenTo3D 1.0.0 / Windows x64
==============================

한국어
------
압축을 모두 푼 뒤 ScreenTo3D.exe를 실행하세요. Python, CUDA Toolkit,
TensorRT SDK, FFmpeg를 따로 설치할 필요는 없습니다. NVIDIA 그래픽 드라이버는
필요합니다. 첫 3D 실행은 이 GPU용 DA2 Small 엔진을 준비하므로 시간이 걸릴 수 있습니다.

실시간 3D: 창이나 모니터 선택 -> 3D 시작.
파일 변환: 영상 추가 -> 깊이 모델과 출력 형식 선택 -> 변환 시작.
입체감 기본값은 0.5, 기본 출력은 Half Top-and-Bottom, VFG는 꺼짐입니다.
실시간 모델은 DA2 Small, 파일 변환의 최초 모델은 DA2 Base입니다.

선택 모델 ZIP을 받은 경우 앱 폴더 옆의 packs 폴더에 두거나 앱의
파일에서 설치를 사용하세요. Base는 비상업용 가중치 조건이 적용됩니다.
VDA Small은 Apache-2.0입니다. NVIDIA VFG는 앱에서 공식 파일을 별도로 받습니다.
Base와 VDA 엔진도 사용자 GPU에서 생성됩니다. oVDA 연구 모델은 본 배포에 포함하지 않습니다.

설정 및 진단 -> 언어에서 시스템 언어, 한국어 또는 English를 선택할 수 있습니다.
패키지의 licenses 폴더와 각 packages/*/LICENSE* 고지를 보존하세요.
릴리스: https://github.com/lesser-vr/ScreenTo3D/releases/tag/v1.0.0

English
-------
Extract all application archives into the same destination, then run
ScreenTo3D.exe. Python, the CUDA Toolkit, TensorRT SDK and FFmpeg are bundled;
an NVIDIA display driver is required. The first DA2 Small session may take
longer while an engine is prepared for your GPU.

Live 3D: select a window or monitor, then Start 3D.
Files: add videos, select a depth model and layout, then start conversion.
Defaults: strength 0.5, Half Top-and-Bottom, VFG off. Live initially uses
DA2 Small; file conversion initially selects DA2 Base and requests installation
if Base is unavailable. You can explicitly choose Small for file conversion.

Place optional model archives in a packs folder next to the app folder, or use
the in-app file installer. Base weights are CC BY-NC 4.0; VDA Small is Apache-2.0.
Their TensorRT engines are built locally on your GPU. Optional NVIDIA VFG is
downloaded separately from NVIDIA and starts disabled. Experimental oVDA is
not included in this portable distribution.

Settings and diagnostics -> Language selects System, Korean or English.
Keep licenses/ and all package license files when redistributing the package.
The prepared runtime requires a GPU supported by bundled CUDA/PyTorch/TensorRT
and CUDA driver API 13.1 or newer. Local hardware validation used RTX 5090;
other GPU and clean-machine compatibility are not certified by that test.
