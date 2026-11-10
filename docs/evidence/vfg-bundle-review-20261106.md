# Veyra 방식 VFG 동봉 검토 — 2026-11-06

## 결론

**공식 NVIDIA wheel의 VFG 전용 DLL 다섯 개를 버전별 앱 전용 폴더에 동봉하는
구성을 기술적 배포 후보로 권장한다.** 이번에는 로컬 후보와 단독 실행을 검증했으며,
현재 앱의 로더·기본값·배포 스크립트를 변경하거나 외부에 배포하지 않았다.
라이선스 권한 판정과 완성된 앱의 포터블 검증은 아직 완료되지 않았다.

NGC 전체 SDK, Python VFX 확장, 불필요한 NPP 라이브러리를 VFG 때문에 함께 넣을
필요는 이번 단독 시험에서 없었다. 다만 DepthSBS 자체의 Python/Qt/Torch/TensorRT
의존성은 별도이며, 이 결과가 앱 전체에서 Python 등을 제거할 수 있다는 뜻은 아니다.

## 실제 파일 구성과 용량

NVIDIA 공개 인덱스에서 아래 wheel 전체를 받아 SHA-256을 검증했다.
Veyra 2.0.3 문서가 지정한 원본과 식별값이 일치한다.

- `nvidia_vfx-0.2.0.0-cp311-cp311-win_amd64.whl`: 435,809,365 bytes.
- SHA-256: `5aaf6a42bc6b6dbbf52fcb714194c994a6893cbbf7ada38bc2165a1f83e4a6fc`.
- 출처: `https://pypi.nvidia.com/nvidia-vfx/`.
- 추출 DLL 다섯 개 모두 Authenticode 상태 Valid, 서명자 NVIDIA Corporation.
- 다섯 DLL은 현재 NGC 1.3.0.0 설치본과 크기는 같지만 SHA-256은 모두 다르다.
  서명 또는 빌드 차이의 원인을 규명하지 않았고, 동일 바이너리로 취급하지 않았다.

| 파일 | bytes | 후보에서의 역할 |
| --- | ---: | --- |
| `NVVideoEffects.dll` | 104,560 | VFX 공통 API |
| `NVCVImage.dll` | 2,694,256 | 이미지 메모리 API |
| `nvVFXVideoFrameGeneration.dll` | 207,321,712 | VFG 기능 |
| `nvngxruntime.dll` | 83,568 | Veyra가 포함하는 NVIDIA 런타임 의존성 |
| `cudart64_12.dll` | 584,304 | CUDA 12 실행 런타임 |
| **DLL 합계** | **210,788,400** | 약 211 MB / 201 MiB |

원본 약관 PDF 세 개, 원본 제삼자 고지 두 개, 모델 NOTICE, 후보 manifest를 함께
묶은 로컬 ZIP은 **187,067,228 bytes**(약 187 MB / 178 MiB)다. 전체 DepthSBS 앱의
설치 용량이 아니라 VFG 구성요소의 증분이며, 설치 압축 방식에 따라 크기는 달라진다.
드라이버 `nvcuda.dll`, 개발 헤더, 샘플, Python 확장 및 다른 효과의 NPP DLL은
이 후보에 포함하지 않았다. 시스템 드라이버와 VC++ 런타임은 계속 필요하다.

## 수행한 실행 검증

기존 `vfg_probe.exe`의 SHA-256이 보관된 NGC 비교 결과의 provenance와 같음을
확인했다: `72501d8ef84b5ecccf3d0ce8e08f8b33f19eb4cb2690ea6cfc298e8a299face0`.
기존 합성 PNG 입력을 각 SHA-256 확인 후 RGBA로 복원했다. 후보 프로세스의 PATH는
Windows/System32로 축소하고, DLL 검색 폴더를 후보의 bin과 feature/bin으로 지정했다.

| 시험 | 결과 |
| --- | --- |
| 640×180 Low, Medium, High | 세 프로세스 모두 성공 종료 |
| 7680×2160 Full SBS Medium, 눈당 3840×2160 | 성공 종료 |
| identity / translation / manual cut / after-cut, 위 네 구성 | 총 16개 RGB 출력이 보관된 NGC 출력과 픽셀 단위 일치. 최대 오차 0 |
| 로드 모듈 경로 샘플링 | 후보 DLL과 Windows/드라이버/VC++ 모듈 및 시험 EXE만 관측. 기존 SDK·Torch·TensorRT·NPP 경로는 관측되지 않음 |

`nvngxruntime.dll`은 이 샘플링에서 로드가 관측되지 않았지만 Veyra의 알려진 의존성
집합에 맞춰 유지했다. 이것은 모든 동적 로드를 포착하는 추적이나 다섯 개가 수학적
최소 집합이라는 증명이 아니다. RGB만 기존 PNG와 비교했으며 알파 계약은 별도다.

최초 네 시험은 과거 raw 입력이 정리되어 identity 입력 파일을 찾지 못하고 종료했다.
DLL 로드 실패는 아니었다. 원본 PNG를 검증·복원한 뒤 `*-v2`로 재시험한 결과가
위 성공 기록이다. 최초 기록은 보존했다.

이 시험은 현재 RTX 5090 환경의 단독 VFG 실행이다. 실제 GUI의 Small/Base 추론과
동시 실행, CUDA 12/13·TensorRT 공존, 새 PC, 장시간 재생, RTX 40/다른 GPU,
VFG High의 4K 지원 범위 또는 실제 SBS FPS를 새로 검증하지 않았다.

## 앱에 적용할 구성안 — 아직 미구현

1. 앱 전용 `runtime/vfg/1.3.0.0/` 아래에 위 DLL과 라이선스를 배치한다. 최초 구현은
   검증한 `bin/` 및 `features/nvvfxvideoframegeneration/bin/` 구조를 유지한다.
   사용자는 별도 NGC 로그인·SDK 설치·모델 다운로드 없이 포함된 파일을 사용한다.
2. `experiments/vfg/native_path.py`가 `run_probe`에서 가져오는 SDK 경로·핀을
   제품용 런타임 로더로 분리한다. 현재 `out/...` 경로를 배포 루트 기준으로 바꾸고,
   패키징 여부에 맞는 경로 해석을 공통화한다. 실험 모듈 import를 제품 의존성으로
   그대로 옮기지 않는다.
3. 공식 wheel과 다섯 DLL 각각의 검증된 해시, 크기, 버전 및 고지를 패키징 manifest에
   고정한다. 현재 세 파일뿐인 검사 범위를 다섯 파일로 확장한다. 기존 NGC 핀을
   무조건 교체하지 않고 새 후보로 등록한다. 임의 DLL 교체 허용은 Veyra에서 따르지 않는다.
4. worker에서만 절대 경로로 로드하고 전역 PATH 변경이나 시스템 폴더 복사를 하지 않는다.
   CUDA 12 런타임과 앱 추론 런타임의 동일 프로세스 공존을 확인한다. 라이브러리 충돌이
   실제로 확인될 때 별도 프로세스를 검토하며, 이번 조사만으로 전송 경계를 추가하지 않는다.
5. `vfg_native_bridge.dll` 등 DepthSBS 자체 바이너리는 별도 패키징한다. VFG SDK가
   지원하는 GPU 범위와 자체 SM120 빌드의 지원 범위를 합쳐서 표시하지 않는다.
   현재 5090 검증을 40 시리즈 지원으로 확장해 홍보할 수 없다.
6. 현재 `scripts/build-v1-portable.ps1`은 파일 변환/예전 GPU Preview 패키지다.
   최신 라이브 GUI와 VFG를 담는 완성된 배포 경로가 아니므로 단순 DLL 복사로 완료되지 않는다.
   Qt 플러그인·worker 실행·모델 캐시·로더 경로까지 포함한 라이브 패키징 작업이 필요하다.
7. 파일 누락·손상·지원되지 않는 GPU·초기화 실패는 시작 전에 명확히 표시한다.
   VFG를 요청했는데 자동으로 다른 결과를 출력하지 않는다. 기존 SBS는 별도로 선택 가능하게 한다.

출시 전 영향 범위에 맞는 검증은 실제 Small/Base+VFG 앱의 출력 비교와 시작/중지/크기
변경, SDK 미설치 PC에서의 실행, 쓰기 권한이 없는 설치 폴더와 사용자별 캐시,
고의 손상/누락 실패 처리다. 재측정 목적은 패키지 호환성이고, 짧은 시험으로 성능·화질
전체를 재인증하지 않는다. 상업 배포 모델은 별도 권한 범위가 검증된 Small을 우선
검토하며 Base의 비상업 가중치 조건을 VFG 약관과 혼동하지 않는다.

## 배포 권한 경계

공식 wheel의 약관은 [이전 검토](vfg-license-review-20261106.md)에서 읽은 NGC
약관과 동일하다. 제품에 포함하는 조건부 재배포 조항은 존재하고, 개발자 프로그램
Enterprise 권한에는 제품 배포 제한이 있다. 익명 공개 wheel의 정확한 제품 분류와
DepthSBS의 취득·배포 권한은 여전히 확정되지 않았다. 따라서 유료 계약이 반드시
필요하다고도, 동봉이 무조건 허용된다고도 단정하지 않는다.

이번 검토는 로컬 후보 구현과 기술적 타당성 확인이다. Veyra의 게시 사실이나 사용자의
동봉 검토 요청을 NVIDIA의 권한 부여로 해석하지 않았다. 제품 배포 범위를 정할 때는
공식 wheel에서 원본 DLL을 선별해 GeForce 고객 PC에 동봉하는 구체적 방식에 적용되는
권한·고지·최종 사용자 약관을 확인해야 한다. 업체 문의는 전송하지 않았다.

## 재현 자료와 출처

- `out/vfg-bundle-review-20261106/inventory.json`: 다운로드 검증과 파일 식별값·용량.
- `signatures.json`, `probe-results-v2.json`, `*-v2.modules.json`, `parity-summary.json`:
  같은 폴더의 서명·실행·경로 관측·RGB 비교 결과.
- `runtime/`, `vfg-runtime-local-review.zip`: 공개 배포하지 않은 로컬 검토 후보.
- 기존 비교 기준: `out/vfg-matrix-20261105/`, `out/vfg-fixtures-20261105/`.
- [Veyra 2.0.3의 다섯 DLL 구성](https://raw.githubusercontent.com/Likely7/Veyra-NRVideo/main/docs/RUNTIME_COMPONENTS_2.0.3.md)
- [NVIDIA 공개 wheel 인덱스](https://pypi.nvidia.com/nvidia-vfx/)
- [현재 제품별 약관 B/F](https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-ai-products/)
