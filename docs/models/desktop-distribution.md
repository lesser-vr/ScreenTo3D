# Windows 데스크톱 배포판

`ScreenTo3D.exe`의 최초 기본값은 실시간 3D에서 DA2 Small, 파일 변환에서 DA2 Base이다. 저장된 사용자 선택이 있으면 복원한다. Small ONNX는 본체에 포함한다. 첫 사용 때 GPU용 엔진을 로컬에 만든다. 파일 변환의 Base를 설치하지 않았다면 설치 안내가 표시되며, Small을 직접 선택할 수도 있다.

실시간 출력 설정의 깊이 모델에서 DA2 Base·VDA Small을 선택하거나 프레임 보간(VFG)을 켜면 필요한 파일의 용량과 조건이 표시된다. 파일 변환도 같은 모델 설치를 공유하며 별도의 입체감·VFG 옵션을 제공한다. 설치 후 사용자가 3D 시작 또는 파일 변환을 누른다.

| 선택 | 다운로드 | 적용 범위 |
|---|---|---|
| 공통 TensorRT 구성요소 | 약 438 MB | 첫 3D 실행 또는 모델 엔진 설치 전에 준비. 전체 런타임·PTX·CUDA 런타임과 고지. |
| 미디어 도구 | 약 92 MB | 파일 변환 첫 실행 전에 FFmpeg·FFprobe와 공유 DLL·고지 설치. |
| DA2 Base | DA2 Base 약 392 MB | 두 화면 비율의 혼합 FP16 ONNX 그래프와 검증 데이터. CC BY-NC 4.0. |
| VDA Small·VDA Small 5프레임 | VDA Small 약 363 MB | 인코더 혼합 FP16 ONNX와 검증 데이터. 두 화면 비율에 대해 첫 프레임·후속 프레임 엔진을 만든다. Apache 2.0. |
| 프레임 보간 | NVIDIA 공식 wheel 약 436 MB | 기본 꺼짐. Small·Base의 지원되는 창 캡처에서 사용한다. wheel을 검증하고 VFG 구성요소와 NVIDIA 고지만 설치한다. |

## 배포 준비

1.0.0 배포 파일과 실행 순서는 [릴리스 안내](../releases/1.0.0.md)에 있습니다.
현재 앱은 `ScreenTo3D-1.0.0-windows-x64.zip` 하나를 직접 풀고 EXE를 실행하면 됩니다.
추출 도구는 체크섬 검사와 팩 일괄 배치를 위한 선택 사항이며 기존 목적지를 덮어쓰지 않습니다.
빌더는 단일 ZIP에서 part 접미사를 생략하고, 여러 ZIP이 필요한 큰 배포본에만 번호를 붙입니다.
선택 모델 ZIP은 앱 옆 `packs/`에 풉니다.

이후 소스 빌더의 기본 출력은 **첫 사용 설치형**입니다. 기존 1.0.0 공개
파일은 변경하지 않습니다. 공통 TensorRT DLL·PTX·CUDA 런타임, 미디어 도구,
엔진 생성에 필요한 GPU 아키텍처별 리소스를 별도 ZIP으로 제공합니다. `runtime-packs/`는
`ScreenTo3D-1.0.0/`와 나란히 둡니다. 추출 도구는 내려받은 런타임 ZIP을 풀지
않고 그대로 그 폴더에 복사하며, 앱이 필요한 팩만 해시 검증 후 설치합니다.
SM75·80·86·89·90·100·120은 해당 팩을 선택하고 그 밖은 전체 호환 팩을 선택합니다.
이는 TensorRT 자체의 GPU 지원 범위를 넓힌다는 뜻은 아닙니다.
예를 들어 SM120 팩은 약 272 MB이며 공통 PTX는 공통 구성요소 팩에 한 번만 들어 있습니다.
다른 GPU에서 만든 엔진을 공유하지 않고 사용자 GPU에서 계속 생성합니다.

팩이 없으면 기존 설치 설정에 용량·NVIDIA 조건과 다운로드/파일 설치 버튼이
나타납니다. 3D 시작·변환 시작을 누르면 필요한 공통 구성요소를 순서대로 설치한 뒤
작업을 이어갑니다. 실패·취소 뒤에는 자동 실행하지 않으며 설치 후 시작을 다시 누릅니다.
Base·VDA 엔진 설치도 필요한 TensorRT 준비를 먼저 수행합니다.
`--bundled-components`는 공통 런타임·미디어 도구를 본체에 포함합니다.
`--full-runtime`은 모든 GPU 리소스까지 포함하는 오프라인 빌드입니다.
소스 실행의 기존 전체 SDK 경로도 유지됩니다.

Base·VDA는 최초 설치 중 준비된 TensorRT로 현재 보이는 첫 번째 NVIDIA GPU에서 엔진을 만든다. 작업 중에는 **이 GPU에 맞게 엔진 최적화 및 검증 중…**이 표시된다. 실시간과 파일 변환이 엔진을 공유하며, GPU UUID, CUDA 드라이버 API 버전, TensorRT 버전 또는 모델 팩이 바뀌면 새 캐시를 사용한다. GPU 교체 후에도 같은 로컬 팩을 다시 사용할 수 있다.

현재 포터블에서 **영상 품질 → 로컬 팩 설치**로 `vda-small-onnx-v3.zip`을 선택한다. v3는 인코더의 12개 블록 모두에 공간 어텐션 FP16을 적용한다. 최초 설치 시 이 GPU용 엔진 4개를 빌드하고 v3 기준 깊이와 이력 텐서를 검증한다. 기존 v1·v2 엔진은 별도 경로에 보관한다. 이전 포터블을 사용 중이면 앱도 함께 갱신한다.

네이티브 CUDA 모듈에는 compute capability 7.5용 PTX와 12.0용 기계어가 들어 있다. CUDA 드라이버 API 13.1 이상, 번들 TensorRT·CUDA가 지원하는 GPU와 해당 모델에 충분한 메모리가 필요하다. 현재 실기기 검증 환경은 RTX 5090이다.

준비된 Windows 체크아웃과 Python 3.11 이상에서 실행한다. 포터블에는 공식 CPython 3.13.9 Windows x64 embeddable ZIP을 사용한다. 빌더는 ZIP과 Small ONNX의 SHA-256을 검사한다.

포터블 빌더는 MSVC 2022 도구로 콘솔 없는 `ScreenTo3D.exe`를 함께 빌드한다.
소스 체크아웃에서는 `scripts/build-desktop-launcher.ps1`로 만든
`out/desktop-launcher/ScreenTo3D.exe`를 저장소 루트에 복사해 실행할 수 있다.
실행 오류창은 `%LOCALAPPDATA%\DepthSBS\logs` 아래의 해당 실행 로그를 안내한다.

네이티브 DLL은 준비된 MSVC·CUDA 개발 환경에서 `scripts/build-portable-cuda.ps1`로 만든다. 패키저는 VDA 입력 모듈을 포함한 각 DLL의 해시를 확인한다. DLL을 새로 빌드하면 결과를 검증한 뒤 릴리스 해시를 갱신한다.

v3 그래프를 재생성할 때는 ONNX·TensorRT 빌드 환경에서 `v1/build_vda_spatial_trial.py`에 고정된 v2 팩, 새 출력 폴더 `out/vda-spatial-b8fc5e47/engines`, `--runtime <TensorRT bin 경로>`를 전달한다. 기본 레시피가 12개 블록을 모두 변환한다. 팩 빌더는 네 그래프의 해시와 아래 명령으로 생성한 ZIP의 해시를 확인한다.

```powershell
python scripts/build-model-packs.py out/desktop-distribution/packs
python scripts/build-desktop-portable.py out/desktop-distribution/ScreenTo3D-1.0.0 `
    --python-zip out/desktop-distribution/python-3.13.9-embed-amd64.zip
python scripts/package-desktop-release.py out/desktop-distribution/ScreenTo3D-1.0.0 `
    out/desktop-distribution/assets --packs out/desktop-distribution/packs
```

온라인 배포 시 두 모델 ZIP, 공통 TensorRT·미디어 도구 ZIP과 GPU 런타임 ZIP을 배포자가 관리하는 HTTPS 경로에 원래 이름으로 게시하고, 포터블 빌드 명령에 `--model-origin <HTTPS 디렉터리 주소>`를 추가한다. 주소는 결과 앱의 `model-origin.txt`에 들어간다. 빌드 스크립트는 업로드하지 않는다. 비공개 GitHub 릴리스 URL을 공개 다운로드 서버로 가정하지 않으며, 자동 다운로드 주소가 없을 때는 내려받은 원본 팩으로 로컬 설치한다. Base 팩에는 모델의 비상업용 조건이 적용된다. VFG는 앱이 직접 [NVIDIA 공식 인덱스](https://pypi.nvidia.com/nvidia-vfx/)의 고정 파일을 요청한다.

공통 팩의 원본 이름은 `tensorrt-11.2.1.2-core-v1.zip`, `ffmpeg-9.0.1-shared-v1.zip`이다. 빌더가 `scripts/build-component-packs.py`를 통해 고정 파일 해시·크기를 검증하고 재현 가능한 ZIP을 만든다. 패키저는 두 ZIP을 앱 ZIP 밖에 배치하고 `component-runtime`으로 기록한다. 추출 도구는 받은 팩만 `runtime-packs/`에 복사한다.

오프라인 전달 시 앱과 `packs/`, 필요한 `runtime-packs/`를 나란히 둔다. 모델은 **로컬 팩 설치**로 가져오고 공통·미디어·GPU 런타임은 첫 작업 전에 검증·설치한다. 별도로 받은 파일은 **파일에서 설치**로 선택한다. VFG는 동일한 버전의 원본 NVIDIA wheel을 선택할 수 있다.

설치는 `%LOCALAPPDATA%\DepthSBS\models` 아래에서 진행한다. SHA-256과 크기가 고정값과 일치해야 압축을 풀고, 취소나 오류 뒤에는 작업 폴더를 정리한다. 최종 폴더는 설치가 완료된 시점에 공개한다. 런타임은 기존 엔진·DLL 검증을 수행한다.

빌더는 개발용 라이브러리·헤더·CMake 파일과 C/C++·CUDA·Cython 소스
(`.c`, `.cc`, `.cpp`, `.cxx`, `.cu`, `.pyx`, `.pxd`, `.pxi`), 미사용 Qt WebEngine을
제외한다. 라이선스 예외는 확장자보다 우선한다. Qt는
`v1/depthsbs_app/qt_portable_profile.json`에 기록한 **PySide6 6.10.2** 구성만
포함하며, 빌더는 다른 버전이나 필수 DLL·PYD가 빠진 입력을 거부한다. 실제 앱의
Python import, QML import scanner와 DLL 의존성을 기준으로 미사용 3D·차트·
멀티미디어·개발 도구 등을 제외한다. QtQuick이 간접 로드하는 QtOpenGL, 파일
선택·별도 오류창용 QtWidgets, 이미지·SVG·PDF·입력기·TLS 플러그인, 컨트롤의
선택적 스타일, 소프트웨어 OpenGL·셰이더 지원과 번역은 보존한다. Qt 버전이나 앱
의존성이 바뀌면 프로필도 재검증한다. 빌드 환경의 `pefile`과
`scripts/check-portable-dependencies.py <앱 폴더> --report <JSON>`으로 Qt의 정적·
지연 로딩 의존성을 확인하며, 동적 로딩은 실제 GUI·파일 선택·출력으로 확인한다.

현재 엔진은 전체 TensorRT 런타임을 사용한다. `nvinfer_lean_11.dll`,
`nvinfer_dispatch_11.dll`, `nvinfer_vc_plugin_11.dll`은 기본·`--full-runtime`
모두에서 제외한다. 전체 추론 DLL, ONNX parser, 일반 플러그인, 공통 PTX와
GPU별 엔진 생성 리소스는 유지한다. 엔진 형식이나 버전 호환 기능을 바꾸면
이 제외 규칙도 다시 확인한다.

FFmpeg는 동일한 Gyan 9.0.1의
고정 SHA-256 공유 빌드를 사용해 ffmpeg/ffprobe 간 라이브러리를 공유한다.
준비 스크립트는 공식 ZIP의 크기·해시와 추출 파일을 검증하며 FFmpeg 고지를
보존한다. Small·Base·VDA와 VFG의 GPU 버퍼는 공통 CUDA 계층이 관리하며,
정식 포터블에는 Torch와 전용 의존 패키지를 넣지 않는다. CUDA Python이 사용하는
CUDA 13.1 `cudart64_13.dll`은 고정 SHA-256으로 검증해 번들한다. 소스 전용
oVDA·RowFlow와 이전 경로의 비교 검증에는 개발 환경의 Torch를 계속 사용할 수 있다.
