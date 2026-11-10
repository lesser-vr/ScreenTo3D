# Owl3D Live 3D 품질 차이 조사 — 2026-11-06

## 결론

좌우 방향 수정 후 사용자는 많이 개선됐지만, Owl3D Live 3D에 비해 일렁거림과
초점이 맞지 않는 느낌이 남는다고 보고했다. 설치된 Live 3D 프로그램의 GPU
셰이더에서 **내용 기반 수렴점, 깊이 변위 제한, 화면 가장자리 돌출 완화,
연속적인 서브픽셀 영상 재구성**을 확인했다. 현재 DepthSBS와 구체적인 차이가 있다.
다만 각 기능이 체감 차이에 기여한 비율은 측정하지 않았다.

가장 먼저 다룰 문제는 DepthSBS 내부에 있다. 최신 프레임을 선택하느라 캡처
번호가 정상적으로 건너뛰어도 깊이 후처리 이력을 초기화한다. 기존 실사용 B
기록 한 건에서는 원본 1,040장 동안 785회 초기화했고, 784회가 이 이유였다.
정상 프레임 생략과 실제 시간 단절을 구분하는 개선을 우선한다.

이번 작업은 **조사와 기록**이다. 앱 처리 코드, Owl3D 설정, 설치 파일은 변경하지
않았다. 새 화면 캡처·영상 기록·모델 실행·프로세스 주입도 하지 않았다.

## 조사 대상과 방법

- 스킬: `reverse-engineer-anything`, 로컬 REA CLI 6.8.0.
- 지원 런타임: 기존 Codex 제공 Node 24.22.1. 시스템 Node 24.18.1은 REA의 요구
  버전에 미달하여 사용하지 않았다. 전역 설치나 MCP 설정 변경은 하지 않았다.
- Owl3D Electron 설치본: 2.4.2. ASAR SHA-256은 기존 조사와 동일한
  `2a62745d1e891e5e9187d9563d22b06f1da983c54dc64f13f77621eaa76cb490`.
- **이번 대상은 Converter가 아니라**
  `AppData/Local/Owl3D/screen_0.0.31/blackwell/Release/display-mirror.exe` 및
  동봉된 셰이더다. EXE SHA-256:
  `17b662fc80aa0aa918b80a714fe6e15256aebede64be3db42bb8b9127841e5f3`.
- REA의 PE imports/desktop inventory를 실제 실행했다. MCP 연결은 없고 Ghidra 등
  native 함수 분석 엔진은 구성되지 않았다. GPU 계산은 설치된 Windows SDK의
  `fxc /dumpbin`으로 DXBC를 디스어셈블하여 별도로 추적했다. 이를 REA 함수
  디컴파일 결과로 표현하지 않는다.
- 11개 원본 셰이더의 해시와 전체 디스어셈블리를
  `out/owl3d-live3d-rea-20261106/shaders/`에 보존했다. 상용 셰이더 코드를 앱에
  복사하거나 가중치를 재배포하지 않았다.

## 발견 사항과 증거 범위

| 질문 | 확인한 내용 | 범위 / 남은 미확인 |
|---|---|---|
| Live 3D가 어떤 경로인가 | 별도 native EXE, D3D11/ONNX Runtime imports. 저장된 실행 로그에서 DepthAnything GPU 초기화, 518/224 모델 및 YOLO 파이프라인 초기화 | 정확한 depth 아키텍처·가중치·학습 출처는 미확인. Converter의 model19/RAFT 결과를 Live 3D에 전용하지 않음 |
| 수렴점이 고정인가 | 공간/깊이 경계 가중 히스토그램의 중앙값을 계산하고, 플래그에 따라 고정값 대신 사용 | 해당 실행의 RawAttentionMode와 호스트 측 시간 완화는 미확인. Attention은 이 셰이더에서 눈의 시선 좌표가 아님 |
| 입체량/가장자리 처리 | P05/P95 기반 변위 배율 및 제한 분기, 화면 좌우 가장자리의 근거리 돌출 완화 | 실제 상수 값과 Comfort LUT 생성 방식 미확인. 생성 셰이더는 sink/popout에 같은 배율을 쓰므로 독립적인 앞뒤 예산이라고 단정하지 않음 |
| 좌우 영상 재구성 | direct/non-direct 모두 거리와 깊이에 따른 연속 가중 합성, 빈 영역의 먼 이웃 및 선형 샘플링 | 저장된 로그가 VIEW-SYNTHESIS 계열 사용을 뒷받침. 정확한 변종과 각 플래그는 미확인 |
| 시간축 안정화 | 조사한 셰이더에는 이전 프레임 깊이/모션 입력이 없음. DepthSBS의 이력 초기화 문제는 코드와 기록으로 확인 | Owl3D 전체의 시간 필터·호스트 캐시·재사용·모델 내부 상태는 아직 미확인. RAFT/optical flow 사용을 주장하지 않음 |
| 개선 순서 | 이력 보존 → 안정적인 수렴점/변위 범위 → 서브픽셀 재구성 | 품질·FPS·시청 편안함은 독립 구현 후 비교 필요 |

### 내용 기반 수렴점

`depth_stats_histogram.asm:156–182`는 화면 가장자리 바깥쪽 15%를 smoothstep으로
감쇠하고, 0.2의 공간 가중치 하한 및 깊이 경계 가중치를 적용한 히스토그램을 만든다.
`depth_stats_finalize.asm:218–252`는 이 히스토그램의 가중 중앙값을 구한다.
`warp_params.asm:92–102`는 유효 플래그와 RawAttentionMode 조건에 따라 이를
수렴점으로 선택한다. 화면 내용에 따른 기준점이며 시선 추적이라는 증거는 아니다.

DepthSBS는 현재 정규화 깊이 0.45를 고정 수렴점으로 쓴다. 장면별 2/98 백분위
재정규화로 동일 물체의 정규화 값이 달라질 수 있어, 고정 수렴점만으로 화면상
깊이를 안정적으로 고정할 수는 없다. 자동 수렴점을 도입해도 빠르게 움직이면
화면 전체의 깊이가 흔들릴 수 있으므로 시간 변화 제한이 필요하다.

### 변위 제한과 가장자리 돌출 완화

`warp_params.asm:92–122`는 선택한 수렴점 C와 P05/P95로
`max(C-p05, p95-C, 0.2)`를 계산한다. BudgetMode 조건에서 이 값에 반비례하는
배율을 만들고, 다른 분기에는 변위와 30을 비교한 제한 계산이 있다. 이 숫자를
현재 디스플레이의 실제 편안함 한계로 해석하지 않는다.

`displacement_precompute_direct.asm:129–172`와 non-direct 대응 코드는 화면
좌우 가장자리의 양의 돌출 변위를 부드럽게 줄이거나 외부 Comfort LUT를 적용한다.
현재 DepthSBS의 균일한 변위 배율에는 이 화면 경계 처리가 없다.

### 서브픽셀 재구성

`backward_warp_direct.asm:208–248`와 `backward_warp.asm:159–195`의 가중치는
`exp(-2 * 투영거리²) * exp(20 * 정규화깊이)`와 동등하다. 투영 위치 주변 1.5픽셀
이내 후보를 합산하고 정규화한다. 가까운 깊이를 강하게 선호하지만 단일 정수
픽셀 소유자를 고르는 방식은 아니다. 구멍에는 먼 쪽 이웃과 선형 샘플링을 쓴다.

DepthSBS는 fractional shift를 floor/ceil에 투영하고 depth 우선 소유자 하나의
RGB를 복사한다. 작은 깊이 변화도 소유자 교체나 1픽셀 윤곽 변화로 나타날 수
있다. 연속적인 재구성은 비교할 가치가 있지만, 부드러움만 늘리면 가림 경계가
흐려질 수 있으므로 얇은 물체·가림·반복 움직임 검증이 필요하다.

## 저장된 실행 로그로 확인한 부분

2026-11-06 02:34 KST 세션의 로그
`display-mirror_20261105_173416_14828_0000.log`:

- RENDERING_PROFILE_STATE: **MORE_POP**. Comfort 모드였다고 가정하지 않는다.
- 첫 변환: `GENERATED_LIVE3D`, `DEPTH518`.
- 244행: 518×518 quality / 224×224 performance 두 깊이 모델 사용 가능.
- 401행: `Using VIEW-SYNTHESIS shader path — depth-budget/edge-fade active`.
- 최종 heartbeat: depth518 crop 500, depth224 crop 94. crop 수는 출력 프레임 수나
  모델 FPS가 아니므로 해당 숫자에서 성능 비교를 계산하지 않았다.

원본 로그의 계정·장치 공통 메타데이터는 보고서에 복제하지 않았다.
`runtime-selected-lines.json`, `runtime-profile-summary.json`에 필요한 필드만 남겼다.
이는 저장된 세션의 관측이며, 현재 화면에 대한 동시 A/B 측정은 아니다.

## DepthSBS의 우선 개선 후보

### 1. 정상 프레임 생략과 깊이 이력 초기화 분리

`live_sbs.py:55`의 reset_reason은 프레임 번호가 연속이 아니면 시간과 관계없이
gap으로 분류한다. GPU capture는 새 프레임이 들어올 때마다 번호를 증가시키고
이전 미처리 프레임을 교체하므로, 추론보다 캡처가 빠를 때 번호 누락은 정상이다.

gap은 `live_gpu_candidate.py:141`에서 reset_pending과 장면 이력 초기화로 이어진다.
다음 `live_depth.cu:112–145` 처리에서 범위와 픽셀 깊이의 시간 안정화가 초기화된다.
VFG는 gap에서 보간 쌍을 유지하지만 먼저 부모 reset을 호출하므로 깊이 이력은
여전히 초기화된다.

| 기존 B 세션 | 원본 | 보간 | 전체 reset | gap / start / cut |
|---|---:|---:|---:|---|
| 20261106-020607-6376 | 1,040 | 1,029 | 785 | 784 / 1 / 0 |
| 20261106-012532-0533 | 4,055 | 4,016 | 1,938 | 1,929 / 1 / 8 |

이 기록은 좌우 방향 수정 이전의 비교 세션이다. 해당 이력 초기화 코드는 현재도
같지만, 이번 불편 신고 직후의 새 측정이라고 주장하지 않는다. 프레임별 source
timestamp가 보존되지 않아 각각의 gap과 보간 시점을 정확히 대응시킬 수 없다.

제안: DA2 Small/Base에서 정상 번호 누락과 실제 시간 단절을 분리한다. 단조 증가
timestamp, 같은 크기, 허용 시간 간격, 장면 전환 없음이면 후처리 이력을 유지한다.
시작·크기 변경·장면 전환·시간 역행·긴 중단은 reset한다. Stateful VDA/oVDA의
모델 이력 규칙까지 한꺼번에 완화하지 않는다. 임계 시간은 비교 실험에서 정한다.

검증: 정상 coalescing의 reset 감소, 정지 물체의 disparity 시간 변화, 장면 전환
잔상, 출력 FPS와 지연. 화면이 부드러워 보이는 짧은 테스트만으로 완료하지 않는다.

### 2. 화면 내용에 맞는 안정적인 수렴점/깊이 범위

고정 0.45 대신 화면 중심/주요 깊이에 기반한 기준점 후보를 독립 구현해 비교한다.
시간 변화율과 근거리 돌출을 제한하고, 물체 진입 시 배경 전체가 움직이는지 측정한다.
UI 옵션을 늘리기보다 내부 A/B로 먼저 평가한다.

### 3. 연속적인 좌우 영상 재구성

현재 depth 우선 가림 관계를 유지하면서 subpixel RGB 재구성을 비교한다.
얇은 선의 출렁임, 경계 잔상, 텍스트 가독성, 비용을 측정한다. 움직임 자체의 깊이
요동이 남으면 모션 정렬 후 이력 결합을 별도 후보로 검토한다. Owl3D가 그 알고리즘을
사용한다고 확인한 것은 아니다.

## 증거 원장 / 제한

| ID 또는 로컬 기록 | 종류 | 보존 위치 |
|---|---|---|
| ev_7679d5cb4b0ddd7d6977724f4adf6130a0e3495fd88de71c327e465e4ba0cba8 | REA PE import 관측 | out/owl3d-live3d-rea-20261106/rea-pe-imports.json |
| ev_269ace9acb942cb3fb96fca9f1b8153052449b174a7b8b507d73c61f7e0c97b8 | REA 설치 디렉터리 관측: 216 entries, 42 files, 14,280 bytes의 선택 헤더 범위 | 같은 폴더의 rea-desktop-observation.json |
| shaders/hashes.json, shaders/FINDINGS.md | Windows SDK 정적 GPU 디스어셈블리, REA Evidence ID 없음 | 같은 폴더의 shaders/ |
| runtime-selected-lines.json, runtime-profile-summary.json | 기존 Owl3D 로그의 선택 필드 | 같은 폴더 |
| depthsbs-reset-summary.json | 기존 DepthSBS 수치 기록의 선택 필드 | 같은 폴더 |
| native-strings.json | EXE ASCII 문자열과 바이트 오프셋; 실행 증거 아님 | 같은 폴더 |

REA desktop CLI의 별도 bundle 파일 쓰기는 권한 오류를 반환했지만, 반환값에 포함된
전체 partial_observation을 그대로 별도 JSON으로 보존했다. 디렉터리 관측은
complete-within-scan이며 전체 파일 내용 해시나 원자적 디렉터리 스냅샷은 아니다.
native 세션을 열지 않았고 CLI 프로세스는 종료됐다. 네이티브 함수 호출 추적과
Owl3D 내부 시간 상태 복원은 미수행이며, 이번 결과를 전체 파이프라인 복원 완료로
표현하지 않는다.
