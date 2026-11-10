# VFG 1.3.0.0 배포 라이선스 검토 — 2026-11-06

공개된 NVIDIA 원문과 현재 로컬 패키지의 라이선스 PDF를 대조한 기록이다.
계정의 주문서·구독·별도 계약은 조회하지 않았으며, NVIDIA의 개별 배포 승인을
받은 기록이 아니다. 실행 결과와 배포 권한은 별개다.

## 판정

**현재 확인된 자료로 DepthSBS의 VFG 포함 배포를 승인할 수 없다.**
VFG 자체가 배포 불가능한 것은 아니다. 모델은 재배포 허용 약관이 있지만,
Core와 기능 실행 라이브러리의 제품 배포 권한도 충족해야 한다.
무료 개발자 프로그램의 Enterprise 제품 권한만으로는 제품 배포가 허용되지 않는다.
현재 다운로드에 적용되는 실제 권한과 고객 PC 배포를 포괄하는 계약은 미확인이다.

## 근거별 구분

| 대상 | 확인된 근거 | DepthSBS에 대한 의미 |
| --- | --- | --- |
| VFG 모델 | 공식 VFG 카탈로그는 NVIDIA Open Model License를 연결한다. 해당 약관 §2.2, §3은 상업 사용과 조건부 재배포를 허용한다. | 모델 권한만으로 SDK 전체 또는 혼합 라이선스 DLL의 배포 권한을 판단하지 않는다. |
| VFX Core / VFG 소프트웨어 | 공식 카탈로그는 NVIDIA Software License Agreement와 AI 제품별 약관을 연결한다. | 모델과 실행 소프트웨어의 권한을 별도로 확인한다. |
| 개발자 프로그램으로 받은 Enterprise 제품 | 동봉 2025-05-05 약관 §1.2.8 및 최신 2026-04-15 약관 F는 내부 평가·개발·테스트로 제한한다. 최신 F는 Customer Product에 포함하지 못한다고 명시한다. | 무료·유료 앱 모두 개발자 권한만으로 제품 배포할 수 없다. 사용자가 직접 다운로드하는 방식도 생산 사용 권한을 대신하지 않는다. |
| 제품에 포함하는 배포 권한 | 동봉 약관 §1.1.3, 최신 B.1 §1.1.2.2에 조건부 재배포 조항이 있다. 주문·라이선스 범위·해당 비용 및 제한을 따른다. | 재배포 경로는 존재한다. 개발자 계정 다운로드나 일반 구독 한 개가 불특정 사용자 배포를 포괄한다고 단정할 수 없다. |

VFG 카탈로그의 commercial/non-commercial use 문구는 기능의 사용 가능성을
설명하지만, 같은 페이지가 연결한 약관의 권한별 제한을 제거하지 않는다.
Core 카탈로그는 AI Enterprise 및 Developer Program 접근을 표시한다.
이 접근 표시만으로 이 사용자의 계약·라이선스 유형을 확정하지 않았다.

Open Model License에 따른 모델 배포에는 약관 사본과 NOTICE의 지정 고지가
필요하다. 소프트웨어는 SLA의 최종 사용자 계약·고지 의무 및 배포되는 각 의존성의
조건도 확인해야 한다. NVIDIA FAQ §7은 제품 통합·재배포용 Embedded License
방식을 설명하지만, VFG/GeForce의 구체적인 가격과 적용 조건을 제시하지 않는다.

## 조사한 로컬 아티팩트

- Core: `out/vfg-sdk-1.3.0.0/VideoFX`.
- VFG: `features/nvvfxvideoframegeneration`, NGC 버전 `1.3.0.0_lib_windows`.
- 기능 폴더는 DLL, 헤더, 의존성 목록, 세 라이선스 PDF를 포함한다. 별도 모델
  가중치 파일 없이 실행됐다는 기존 기술 검증은 DLL 전체의 라이선스 분류를 뜻하지 않는다.
- Core와 VFG 폴더의 제품별 약관 및 Open Model License PDF 해시가 일치한다.

| 동봉 문서 | SHA-256 |
| --- | --- |
| `NVIDIA-Software-License-Agreement-2025.05.05.pdf` (Core) | `887d7381eed7cd2e6d9fbfa9c9bbda4e32df20bf506cff79dc5c8dae20ccc531` |
| `product-specific-terms-for-nvidia-ai-products-2025.05.05.pdf` | `5c755ab1145deb6ce422c2d376f4c3adb55da9f6f2492f35e6d4759e7e3e5499` |
| `NVIDIA-Open-Model-License-Agreements-24-10-2025.pdf` | `4d2fb590aa9b30c47f2058bff17291df7fa2aa0c1bd775a20703da9bb267cfab` |

## NVIDIA에 확인할 미해결 사항

문의 대상은 VFX SDK Core `1.3.0.0_windows`와
`nvvfxvideoframegeneration:1.3.0.0_lib_windows`다. DepthSBS는 Windows에서
최종 사용자의 로컬 GeForce GPU로 SBS 영상의 프레임을 보간하는 데스크톱 앱이다.

1. 이 두 패키지가 무료 생산 사용·재배포 가능한 Community 제품인지, 별도
   Enterprise/Embedded 계약이 필요한지, 그 판단의 제품별 문서.
2. 무료 앱과 유료 앱 각각의 바이너리 동봉 및 별도 설치 팩 배포 허용 범위.
3. 고객의 GeForce RTX 40/50 계열 PC에서의 사용 권한, 사용자별 NVIDIA 계정·구독
   필요 여부, 과금 단위와 최소 계약 조건. 기술적 GPU 지원과 라이선스는 별개다.
4. VFG DLL 내부 모델과 실행 코드의 라이선스 구분, 허용 재배포 파일 목록,
   최종 사용자 약관·고지·업데이트·계약 종료 시 의무.
5. 공급자가 제공하는 공개 다운로드 또는 `nvidia-vfx` 배포 채널에 별도의
   생산 사용 권한이 있는지. 공개 접근이나 패키지 메타데이터만으로 허용을 추정하지 않는다.

문의는 전송하지 않았다. 계정 비밀정보를 읽거나 복사하지 않았다.
현재 런타임·설치 팩·자동 다운로드 구현은 변경하지 않았다.

## 1차 출처

- [VFG 공식 카탈로그](https://catalog.ngc.nvidia.com/orgs/nvidia/maxine/collections/nvvfxvideoframegeneration/-)
- [Core 공식 카탈로그](https://catalog.ngc.nvidia.com/orgs/nvidia/maxine/resources/vfx_sdk_core/-)
- [동봉본과 같은 날짜의 제품별 약관, 2025-05-05](https://www.nvidia.com/content/dam/en-zz/Solutions/license-agreements/enterprise-software/product-specific-terms-for-nvidia-ai-products-5may2025.pdf)
- [최신 제품별 약관, 2026-04-15](https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-ai-products/)
- [NVIDIA Software License Agreement, 2026-05-07](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/)
- [NVIDIA Open Model License, 2025-10-24](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/)
- [라이선스 FAQ: Embedded Licensing §7 및 Partner & Embedded Licensing](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-licensing-overview-and-faq/)

구형 Maxine SDK의 재배포 안내, 샘플 코드의 MIT 라이선스, Open Model License만으로
현재 NGC 1.3.0.0 런타임의 배포 권한을 대체하지 않았다. `nvidia-vfx` 0.2.0.0의
공개 메타데이터는 NVIDIA 독점 라이선스를 표시하지만, 그 wheel 내부 약관은 이번에
검토하지 않았으므로 대체 배포 경로로 승인하지 않았다.
