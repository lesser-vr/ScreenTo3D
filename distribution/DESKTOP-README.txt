ScreenTo3D 1.0.1 / Windows x64
==============================

한국어
------
압축을 모두 푼 뒤 ScreenTo3D.exe를 실행하세요. Python, CUDA Toolkit,
TensorRT SDK, FFmpeg를 수동으로 설치할 필요는 없습니다. NVIDIA 그래픽 드라이버는
필요합니다. 첫 3D 실행은 필요한 TensorRT 구성요소를 설치하고 이 GPU용 DA2 Small
엔진을 준비합니다. 파일 변환 첫 사용에는 FFmpeg도 설치하므로 시간이 걸릴 수 있습니다.
설치가 끝나면 요청한 작업을 계속합니다. 취소하면 실행하지 않습니다.
필수 파일이 없으면 오류창 없이 준비 화면으로 연결됩니다. TensorRT·CUDA·FFmpeg·VFG는
고정된 공식/빌드 제공처에서 로그인 없이 직접 받습니다. TensorRT 원본은 약 1.96GB이며
공통·GPU별 설치에서 재사용합니다. 다운로드 파일은 캐시에 보관하고 중단 시 이어받습니다.
Small 모델은 앱에 포함됩니다. Base·VDA 변환 팩은 별도 공개 모델 저장소에서
로그인 없이 받고, 크기·해시 확인 후 이 GPU용 엔진을 준비합니다. 모델 선택만으로는
다운로드하지 않습니다. 준비 취소·실패 후에는 작업을 다시 시작하세요.
설정은 앱 폴더의 data/settings.ini, 모델·런타임·캐시·로그도 data 아래에 저장합니다.
앱 폴더를 옮길 때는 data 폴더를 함께 옮기세요. 저장 위치는 설정 및 진단에서 확인할 수 있습니다.
업데이트할 때 앱을 닫고 프로그램 파일을 교체하되 data 폴더는 유지하세요.
다른 사용자·GPU에서는 엔진을 다시 준비할 수 있습니다. 앱 폴더 삭제 시 이 복사본의
데이터도 삭제됩니다.
GPU별 런타임 ZIP을 받은 경우 앱 폴더 옆 runtime-packs 폴더에 원래 이름으로
두세요. 앱이 GPU에 맞는 파일만 검증·설치합니다. 파일이 없으면 설치 설정에서
GPU 런타임을 설치하세요. 공통 TensorRT·미디어 도구 팩도 같은 폴더에 둘 수 있습니다.
오프라인 빌드는 필요한 런타임과 모델이 모두 동봉된 경우 추가 다운로드가 없습니다.

실시간 3D: 창이나 모니터 선택 -> 3D 시작.
3D는 보이는 상태로 유지하고 키보드·마우스는 원본 창에서 조작하세요.
제목표시줄 이동·테두리 크기 조절·우클릭 메뉴를 마치면 원본 조작으로 돌아갑니다.
Ctrl+Alt+Enter로 원본 조작 중 전체화면을 전환합니다. 실시간 출력 설정에도 버튼이 있습니다.
3D 창에서 F11로 전체화면에 진입하고, 원본 창에서 F11로 창 모드로 돌아옵니다.
VFG 전환은 Ctrl+Alt+S입니다.
메인 화면 상단 ? 또는 실시간 출력 설정의 조작·단축키 안내에서 사용 조건을 확인하세요.
파일 변환: 영상 추가 -> 깊이 모델과 출력 형식 선택 -> 변환 시작.
입체감 기본값은 0.5, 기본 출력은 Half Top-and-Bottom, VFG는 꺼짐입니다.
실시간 모델은 DA2 Small, 파일 변환의 최초 모델은 DA2 Base입니다.

원본 모델 ZIP의 파일에서 설치도 지원합니다. 별도 동봉 빌드의 packs 폴더는 보존하세요.
Base는 비상업용 가중치 조건이 적용됩니다.
VDA Small은 Apache-2.0입니다. NVIDIA VFG는 앱에서 공식 파일을 별도로 받습니다.
Base와 VDA 엔진도 사용자 GPU에서 생성됩니다. oVDA 연구 모델은 본 배포에 포함하지 않습니다.

설정 및 진단 -> 언어에서 시스템 언어, 한국어 또는 English를 선택할 수 있습니다.
한글·영문용 Pretendard 글꼴도 앱에 포함되어 별도로 설치할 필요가 없습니다.
오류창 내용은 data/logs/errors.jsonl에 발생 시각·오류 ID·상세 내용과 함께 저장됩니다.
창을 닫아도 남으며, 약 1MB마다 errors.1.jsonl 한 개를 이전 기록으로 보관합니다.
기록은 이 앱 폴더에만 저장하며 자동 업로드하지 않습니다.
패키지의 licenses 폴더와 각 packages/*/LICENSE* 고지를 보존하세요.
릴리스: https://github.com/lesser-vr/ScreenTo3D/releases/tag/v1.0.1

English
-------
Extract all application archives into the same destination, then run
ScreenTo3D.exe. Python is bundled; an NVIDIA display driver is required.
The app installs common TensorRT components on first Start 3D and media tools
on first file conversion, then continues your requested task. Cancelling setup
keeps the task stopped. DA2 Small stays bundled; engines are built for your GPU.
Missing files open setup directly without an error. Pinned TensorRT/CUDA, FFmpeg
and VFG archives download directly from their publishers without signing in.
The original TensorRT archive is about 1.96 GB and reused for common/GPU resources.
Downloads are cached and interrupted transfers can resume. Small stays in the app.
Converted Base/VDA packs download from the separate public model repository without
sign-in, then their GPU engines are prepared. Selecting a model alone does not download it.
Cancellation or failure keeps the task stopped until you start it again.
Settings use data/settings.ini in the app folder; models, runtimes, caches and
logs also stay under data/. Error-window reports stay in data/logs/errors.jsonl
with timestamps, error IDs and available details after dismissal. At about 1 MiB,
errors.1.jsonl keeps one previous log. These local records are not uploaded.
The current storage path is shown in Settings and diagnostics.
Move the whole app folder, including data/. Close the app before updating program files and keep
data/. A different user/GPU may need new engines. Deleting this app folder removes
its local data.
For GPU-selected bundles, keep the matching runtime ZIP under runtime-packs/
next to the app folder, using its original name. The app verifies and installs
only the required resource. If absent, install the GPU runtime from installation
settings. Common TensorRT and media component ZIPs also belong in runtime-packs/.
Offline builds need no downloads when all required runtimes and models are included.

Live 3D: select a window or monitor, then Start 3D.
Keep keyboard and mouse input in the original window while viewing 3D.
Title-bar moves, border resizing and right-click menus return to original input when finished.
Ctrl+Alt+Enter toggles fullscreen globally; Live output settings also provide a button.
Press F11 while controlling the 3D window to enter fullscreen, then F11 from the
source window to return to windowed mode. VFG uses Ctrl+Alt+S.
Open ? on the main screen or Controls and shortcuts in Live output settings for help.
Files: add videos, select a depth model and layout, then start conversion.
Defaults: strength 0.5, Half Top-and-Bottom, VFG off. Live initially uses
DA2 Small; file conversion initially selects DA2 Base and requests installation
if Base is unavailable. You can explicitly choose Small for file conversion.

Preserve packs/ in an explicitly bundled offline build. Original model ZIPs work with the
in-app file installer. Base weights are CC BY-NC 4.0; VDA Small is Apache-2.0.
Their TensorRT engines are built locally on your GPU. Optional NVIDIA VFG is
downloaded separately from NVIDIA and starts disabled. Experimental oVDA is
not included in this portable distribution.

Model packs: https://github.com/lesser-vr/ScreenTo3D-Models/releases/tag/packs-2026.11.1

Settings and diagnostics -> Language selects System, Korean or English.
The bundled Pretendard typeface needs no separate font installation.
Keep licenses/ and all package license files when redistributing the package.
The prepared runtime requires a GPU supported by bundled CUDA/TensorRT
and CUDA driver API 13.1 or newer. Local hardware validation used RTX 5090;
other GPU and clean-machine compatibility are not certified by that test.
