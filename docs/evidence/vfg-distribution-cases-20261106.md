# VFG 배포 사례 조사 — 2026-11-06

범위: 실제 공개 통합·배포 방식과 NVIDIA 런타임 취득 경로. 타 프로젝트의
비공개 계약 또는 법적 적합성을 판정하지 않았으며 앱 설치·성능 시험은 하지 않았다.
기존 [NGC 패키지 약관 검토](vfg-license-review-20261106.md)를 보완한다.

## 결과

NGC 로그인 방식 외에 NVIDIA가 공개 배포하는 `nvidia-vfx` wheel 경로가 있다.
Comfy-Org는 이를 의존성으로 설치하고, Veyra는 동일 계열 wheel의 네이티브 DLL을
선별해 동봉한다고 문서화한다. 따라서 VFG 설치에 NGC 가입이 항상 필요하다거나,
모든 VFG 이용에 유료 Enterprise 구독이 필수라고 일반화할 근거는 없다.

그러나 공개 wheel의 핵심 약관은 현재 NGC 패키지와 동일하다. 공개 접근 자체는
제품 분류나 재배포 권한의 확정 증거가 아니다. 개발자 프로그램 Enterprise 권한의
제한을 공개 wheel 취득자 모두에게 자동 적용할 수도 없다. 남은 쟁점은 공식 공개
wheel의 Community/Enterprise 분류와 DepthSBS의 취득·배포에 적용되는 권한이다.

## 사례

| 사례 | 공개적으로 확인한 방식 | 참고점 / 증거 한계 |
| --- | --- | --- |
| Comfy-Org `ComfyUI_Nvidia_VFX_Nodes` | RTX Video Frame Generation 노드 제공. `requirements.txt`는 `nvidia-vfx>=0.2`; Manager 또는 pip로 의존성 설치. 노드 코드는 Apache-2.0, NVIDIA 라이브러리는 별도 독점 라이선스. | 직접 VFG 사례. 사용자 환경에 NVIDIA 패키지를 설치하는 방식의 가장 강한 참고 사례. Comfy와 NVIDIA 사이 계약은 미확인. |
| Veyra-NRVideo 2.0.3 문서 | NVIDIA 휴대용 패키지에 VFG용 원본 DLL 다섯 개를 동봉한다고 명시. 원본은 공식 `nvidia-vfx` 0.2.0.0 Windows wheel. | 직접 VFG 동봉 사례. 문서 스스로 일반 재배포 허가나 NVIDIA 인증의 근거가 아니라고 밝힌다. Release ZIP 내부를 이번에 검증하지 않았다. |
| `ComfyUI-FL-RTXVSR` | 최초 사용 시 NVIDIA 패키지 인덱스에서 고정 버전 0.1.0.1 wheel을 다운로드하고 SHA-256 검증 후 전용 폴더에 추출. 자체 저장소는 NVIDIA 바이너리를 재배포하지 않는다고 명시. | VFG가 아닌 VSR 사례. DepthSBS의 선택적 구성요소 설치·캐시·무결성 검증 UX 참고용이며 VFG 배포 허가의 증거는 아니다. |
| NVIDIA Broadcast 2.3 / ComfyUI 공식 발표 | NVIDIA는 Broadcast의 베타 영상 프레임 생성과 ComfyUI의 15→60 fps 보간을 공식 발표했다. | 소비자 PC에서 공개 제공되는 기능이라는 근거. NVIDIA 자체 앱의 배포 권한이 DepthSBS에 이전되지는 않는다. |

Veyra 문서의 VFG 전용 파일은 `NVVideoEffects.dll`, `NVCVImage.dll`,
`nvVFXVideoFrameGeneration.dll`, `nvngxruntime.dll`, `cudart64_12.dll`이며,
합계 210,788,400 bytes(약 211 MB)로 기록되어 있다. Python 및 불필요한 NPP
라이브러리를 제외하는 기술적 구성 사례다. DepthSBS의 현재 검증된 DLL을 이 파일로
교체하거나 동일 동작을 검증한 것은 아니다.

## 공식 wheel 직접 확인

- NVIDIA 공개 인덱스 `https://pypi.nvidia.com/nvidia-vfx/`를 인증 없이 조회했다.
- 대상: `nvidia_vfx-0.2.0.0-cp311-cp311-win_amd64.whl`.
- 인덱스가 표시하는 SHA-256:
  `5aaf6a42bc6b6dbbf52fcb714194c994a6893cbbf7ada38bc2165a1f83e4a6fc`.
- 서버가 보고한 전체 크기: 435,809,365 bytes. Veyra 문서의 원본 식별값과 일치한다.
- HTTP Range로 ZIP 디렉터리·라이선스·메타데이터만 851,766 bytes 읽었다.
  전체 wheel을 내려받아 해시 검증한 것은 아니다. 네이티브 코드는 로드하지 않았다.
- `METADATA`는 `LicenseRef-NvidiaProprietary`를 표시하며, 런타임 라이브러리가
  wheel 안에 포함된다고 설명한다.
- 추출한 Software License Agreement 2025-05-05, AI 제품별 약관 2025-05-05,
  Open Model License 2025-10-24의 SHA-256은 앞선 NGC 패키지 검토의 세 값과
  모두 일치했다. 별도 제삼자 고지 두 파일도 확인했다.
- 관측 기록과 추출한 문서: `out/vfg-license-cases-20261106/manifest.json` 및 같은 폴더.

이는 익명 다운로드 가능성과 약관 동일성을 입증한다. Community 제품 분류,
개발자 프로그램 권한 적용 여부, GeForce 고객 PC 배포 계약, 실제 런타임 호환성을
확정하는 검증은 아니다. NVIDIA의 공개 안내를 함께 고려하면 NGC 취득 경로만으로
일괄 유료 계약을 단정하는 대신 공개 wheel 경로를 별도로 검토할 이유가 있다.

## DepthSBS에 대한 제안

설계 후보는 ComfyUI처럼 공식 NVIDIA 패키지를 사용자 환경에 선택적으로 설치하는
방식이다. Veyra는 최소 실행 파일 구성의 참고 자료로 사용한다. 우리 서버에서
DLL 설치 팩을 재배포하는 방식은 그에 맞는 권한을 별도로 확인한다.

라이선스 문의는 다음처럼 좁힐 수 있다: 공식 공개 `nvidia-vfx` 0.2.0.0 Windows
wheel을 GeForce 사용자가 직접 다운로드하여 무료 또는 유료 데스크톱 앱에서
실행하는 경우 Community 제품 권한이 적용되는지, 그리고 공급자가 필요한 원본
DLL만 선별해 고객 PC에 배포할 수 있는지. 이는 별도의 NGC 개발자 프로그램
Enterprise 다운로드와 동일한 취득 권한인지도 확인 대상이다.

현재 앱·SDK 경로·배포 파일은 변경하지 않았고, 업체 또는 프로젝트에 문의를
전송하지 않았다. 지원 범위나 법적 허가를 사례만으로 확정하지 않았다.

## 출처

- [Comfy-Org 공식 노드](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes)
- [설치 의존성](https://raw.githubusercontent.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes/main/requirements.txt)
- [Comfy 제품 안내와 라이선스 구분](https://comfy.org/nvidia-vfx)
- [Veyra 2.0.3 구성 문서](https://raw.githubusercontent.com/Likely7/Veyra-NRVideo/main/docs/RUNTIME_COMPONENTS_2.0.3.md)
- [Veyra 제삼자 고지의 VFG 항목](https://github.com/Likely7/Veyra-NRVideo/blob/main/THIRD_PARTY_NOTICES.md#nvidia-video-frame-generation-local-integration-2026-10-03)
- [Veyra 공개 릴리스](https://github.com/Likely7/Veyra-NRVideo/releases)
- [FL-RTXVSR 다운로드 방식](https://github.com/filliptm/ComfyUI-FL-RTXVSR)
- [NVIDIA 공식 RTX Spark 출시 발표: Broadcast 및 ComfyUI](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-RTX-Spark-PCs-Available-Today--A-New-Beginning-for-Windows-PCs/default.aspx)
- [NVIDIA 공개 패키지 인덱스](https://pypi.nvidia.com/nvidia-vfx/)
- [NVIDIA wheel 설명·버전·소유자](https://pypi.org/project/nvidia-vfx/)

GitHub main 문서와 웹 페이지는 조사 시점의 공개 자료다. 버전 특정 사례는
문서에 명시된 2.0.3 / 0.2.0.0 / 0.1.0.1 범위로 한정한다.
