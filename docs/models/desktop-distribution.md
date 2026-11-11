# Windows 데스크톱 배포판

`ScreenTo3D.exe`의 최초 기본값은 실시간 3D에서 DA2 Small, 파일 변환에서 DA2 Base이다. 저장된 사용자 선택이 있으면 복원한다. Small ONNX는 본체에 포함한다. 첫 사용 때 GPU용 엔진을 로컬에 만든다. 파일 변환의 Base를 설치하지 않았다면 설치 안내가 표시되며, Small을 직접 선택할 수도 있다.

실시간 출력 설정의 깊이 모델에서 DA2 Base·VDA Small을 선택하거나 프레임 보간(VFG)을 켜면 필요한 파일의 용량과 조건이 표시된다. 파일 변환도 같은 모델 설치를 공유하며 별도의 입체감·VFG 옵션을 제공한다. 설치 후 사용자가 3D 시작 또는 파일 변환을 누른다.

| 선택 | 다운로드 | 적용 범위 |
|---|---|---|
| DA2 Base | DA2 Base 약 392 MB | 두 화면 비율의 혼합 FP16 ONNX 그래프와 검증 데이터. CC BY-NC 4.0. |
| VDA Small·VDA Small 5프레임 | VDA Small 약 363 MB | 인코더 혼합 FP16 ONNX와 검증 데이터. 두 화면 비율에 대해 첫 프레임·후속 프레임 엔진을 만든다. Apache 2.0. |
| 프레임 보간 | NVIDIA 공식 wheel 약 436 MB | 기본 꺼짐. Small·Base의 지원되는 창 캡처에서 사용한다. wheel을 검증하고 VFG 구성요소와 NVIDIA 고지만 설치한다. |

## 배포 준비

1.0.0 배포 파일과 실행 순서는 [릴리스 안내](../releases/1.0.0.md)에 있습니다.
여러 앱 ZIP은 같은 새 디렉터리에 합쳐 풀며, 함께 제공하는 추출 도구는 SHA-256을
검증하고 기존 목적지를 덮어쓰지 않습니다. 선택 모델 ZIP은 앱 옆 `packs/`에 풉니다.

Base·VDA는 최초 설치 중 포터블에 포함된 TensorRT로 현재 보이는 첫 번째 NVIDIA GPU에서 엔진을 만든다. 작업 중에는 **이 GPU에 맞게 엔진 최적화 및 검증 중…**이 표시된다. 실시간과 파일 변환이 엔진을 공유하며, GPU UUID, CUDA 드라이버 API 버전, TensorRT 버전 또는 모델 팩이 바뀌면 새 캐시를 사용한다. GPU 교체 후에도 같은 로컬 팩을 다시 사용할 수 있다.

현재 포터블에서 **영상 품질 → 로컬 팩 설치**로 `vda-small-onnx-v3.zip`을 선택한다. v3는 인코더의 12개 블록 모두에 공간 어텐션 FP16을 적용한다. 최초 설치 시 이 GPU용 엔진 4개를 빌드하고 v3 기준 깊이와 이력 텐서를 검증한다. 기존 v1·v2 엔진은 별도 경로에 보관한다. 이전 포터블을 사용 중이면 앱도 함께 갱신한다.

네이티브 CUDA 모듈에는 compute capability 7.5용 PTX와 12.0용 기계어가 들어 있다. CUDA 드라이버 API 13.1 이상, 번들 TensorRT·PyTorch가 지원하는 GPU와 해당 모델에 충분한 메모리가 필요하다. 현재 실기기 검증 환경은 RTX 5090이다.

준비된 Windows 체크아웃과 Python 3.11 이상에서 실행한다. 포터블에는 공식 CPython 3.13.9 Windows x64 embeddable ZIP을 사용한다. 빌더는 ZIP과 Small ONNX의 SHA-256을 검사한다.

포터블 빌더는 MSVC 2022 도구로 콘솔 없는 `ScreenTo3D.exe`를 함께 빌드한다.
소스 체크아웃에서는 `scripts/build-desktop-launcher.ps1`로 만든
`out/desktop-launcher/ScreenTo3D.exe`를 저장소 루트에 복사해 실행할 수 있다.
실행 오류창은 `%LOCALAPPDATA%\DepthSBS\logs` 아래의 해당 실행 로그를 안내한다.

네이티브 DLL은 준비된 MSVC·CUDA 개발 환경에서 `scripts/build-portable-cuda.ps1`로 만든다. 패키저는 VDA 입력 모듈을 포함한 각 DLL의 해시를 확인한다. DLL을 새로 빌드하면 결과를 검증한 뒤 릴리스 해시를 갱신한다.

v3 그래프를 재생성할 때는 ONNX·TensorRT 빌드 환경에서 `v1/build_vda_spatial_trial.py`에 고정된 v2 팩, 새 출력 폴더 `out/vda-spatial-b8fc5e47/engines`, `--runtime <TensorRT bin 경로>`를 전달한다. 기본 레시피가 12개 블록을 모두 변환한다. 팩 빌더는 네 그래프의 해시와 아래 명령으로 생성한 ZIP의 해시를 확인한다.

```powershell
python scripts/build-model-packs.py out/desktop-distribution/packs
python scripts/build-desktop-portable.py out/desktop-distribution/DepthSBS `
    --python-zip out/desktop-distribution/python-3.13.9-embed-amd64.zip
```

온라인 배포 시 두 ZIP을 배포자가 관리하는 HTTPS 경로에 원래 이름으로 게시하고, 포터블 빌드 명령에 `--model-origin <HTTPS 디렉터리 주소>`를 추가한다. 주소는 결과 앱의 `model-origin.txt`에 들어간다. 빌드 스크립트는 업로드하지 않는다. Base 팩에는 모델의 비상업용 조건이 적용된다. VFG는 앱이 직접 [NVIDIA 공식 인덱스](https://pypi.nvidia.com/nvidia-vfx/)의 고정 파일을 요청한다.

오프라인 전달 시 `DepthSBS/`와 `packs/`를 나란히 두면 필요한 모델만 **로컬 팩 설치**로 가져온다. 별도로 받은 파일은 **파일에서 설치**로 선택한다. VFG는 동일한 버전의 원본 NVIDIA wheel을 선택할 수 있다.

설치는 `%LOCALAPPDATA%\DepthSBS\models` 아래에서 진행한다. SHA-256과 크기가 고정값과 일치해야 압축을 풀고, 취소나 오류 뒤에는 작업 폴더를 정리한다. 최종 폴더는 설치가 완료된 시점에 공개한다. 런타임은 기존 엔진·DLL 검증을 수행한다.
