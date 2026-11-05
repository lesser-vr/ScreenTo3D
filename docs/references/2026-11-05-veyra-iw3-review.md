# Veyra / iw3 적용 가능성 조사 — 2026-11-05

소스·공식 문서 조사 결과다. 프로그램 설치, SDK/모델 다운로드, 새 성능 측정이나
HMD 실험은 수행하지 않았다. 아래 우선순위는 이번 조사의 제안이며 제품 지원 상태나
확정 로드맵을 변경하지 않는다. DepthSBS 비교 기준은 `40735a6`이다.

## 결론

적용 가치가 가장 큰 것은 **GPU 캡처·전처리**, **iw3 학습형 SBS 합성 비교**,
**NVIDIA VFG의 별도 가능성 실험**이다. Veyra의 큐·시간 관리와 iw3의 자동 수렴점은
후속 후보다. 지금의 작은 Qt 제어창을 유지하면서 내부 처리에 적용할 수 있다.

Veyra의 영상 보정·프레임 생성과 iw3의 깊이·입체 합성은 역할이 다르다.
Veyra의 일반 영상 재생 결과를 양안 SBS 품질이나 DepthSBS의 4K60 증거로 간주하지 않는다.
설계 아이디어 참고, 소스 코드 재사용, 모델/런타임 배포를 각각 구분한다.

## 확인한 버전과 개발 브랜치

| 대상 | 조사 스냅샷 | 확인 사항 |
|---|---|---|
| Veyra-NRVideo `main` | `fedd7fc29b9adbc13defd13d0c718a9db3d128ed` | README의 현재 버전은 2.1.2. 배포 EXE에 대응하는 제품 소스는 별도 `358be8c`로 기록되어 있으므로 main과 배포 바이너리를 혼동하지 않음 |
| nunif/iw3 `master` | `0d3d92c8f4396da564c44524b6390ee5c76b9668` | 커밋 시각 2026-10-20 UTC. GPU 캡처, 학습형 합성, 자동 수렴점, inpainting 등이 이미 포함 |
| nunif/iw3 `dev` | `448e57962f49233432aac638996395f233d8d9cc` | 커밋 시각 2026-11-05 UTC. master보다 37커밋 앞섬, 뒤처짐 0 |
| iw3 `passthrough` | `143c546de22b4dc49f88bb81c82e7b7e0ff48024` | alpha/AR 작업이 PR #753을 통해 dev에 병합되어 있음 |

현재 브랜치 목록에는 과거의 `iw3_inpaint`가 없다. inpainting 기능은 master의
`base_inpaint.py`, `forward_inpaint.py`, `mlbw_inpaint.py` 등에 존재한다.
다른 날짜 브랜치와 Python/waifu2x 전용 브랜치 전체를 감사한 것은 아니다.

근거: [Veyra 브랜치][v-branches], [Veyra 빌드 기록][v-build],
[iw3 브랜치][i-branches], [고정 master/dev 비교][i-compare].

## DepthSBS와의 실제 차이

- 현재 Base/VDA/oVDA는 깊이 결과와 SBS 처리를 GPU에 유지한다. 그러나 WGC 입력은
  CPU에 매핑한 배열이며 Base는 `frame / 255.0` 뒤 OpenCV cubic resize와 정규화를
  수행하고 다시 GPU로 올린다. 입력 GPU화는 이미 완료한 출력 GPU화와 다른 작업이다.
- Base의 기존 측정은 4K 입력/7680×2160 SBS에서 기본 host 출력 6.46fps,
  명시적 native 출력 8.43fps다. native의 aggregate depth는 98.46ms, SBS는 15.84ms였다.
  이 depth 시간에는 전처리·추론·크기 복원·검증이 함께 들어가므로 순수 모델 한계가 아니다.
  측정은 확대된 공개 1080p 영상과 축소 표시 창을 사용한 짧은 구간이며 물리 화면 FPS가 아니다.
- 기존 사용자 iw3 설정의 과거 스냅샷에는 이미 `row_flow_v3_sym`, DA2 Small,
  `wc_mp`, Full SBS가 기록되어 있다. 학습형 합성을 비교하면 기존 기준선과의
  품질 차이가 깊이 모델 때문인지 합성기 때문인지 분리하는 데 도움이 된다.
- DepthSBS에는 최신 프레임 한 슬롯, 시간 정보, 오류·중지·캡처 제외, native texture
  수명 관리가 이미 있다. 같은 기능을 새 기능처럼 다시 이식할 필요는 없다.

로컬 근거: [현재 상태](../implementation-status.md),
[Base 측정](../evidence/da2-base-device-20261105.md),
[기준선 설정 기록](../evidence/p0-depth-attribution.md),
`v1/depthsbs_app/{capture_worker,da2_base,da2_base_device,presentation_policy}.py`.

## 후보별 판단

### 1. GPU 캡처와 모델 입력 전처리 — 최우선 성능 후보

iw3의 `wc_cuda` 경로는 WGC 프레임을 CUDA tensor로 받아 색상 변환·크기 조절을 GPU에서
수행한다. 실제 wc_cuda 구현에는 D3D11 texture 등록, device-to-device 복사,
전용 stream 동기화가 있으므로 복사가 전혀 없는 구조는 아니다. Veyra도 WGC의 D3D11
texture를 공유 리소스·fence로 D3D12 소비자에게 전달한다. [iw3 캡처][i-capture],
[wc_cuda][wc], [Veyra 캡처][v-capture]

DepthSBS에는 WGC → CUDA → GPU resize/normalize → TensorRT 경로가 적합하다.
Veyra 전체의 D3D12 엔진으로 교체할 필요는 없다. 먼저 CPU 전처리만 GPU화하여 이득을
분리 측정하고, 이어서 캡처 readback 제거를 측정하는 편이 원인 파악에 유리하다.

주의할 구현 차이:

- 현재 Base의 float64/OpenCV cubic 전처리를 단순 torch resize로 바꾸면 수치가 달라진다.
  동등성 최적화로 진행할 때는 기존 비교 기준을 지켜야 하고, 의도적인 변경은 새 품질 비교가 필요하다.
- wc_cuda의 예제 경로는 창 이름을 사용한다. 현재 HWND/PID 명시 선택·재사용 방지 계약을 유지해야 한다.
- iw3 캡처 wrapper의 일부 창 크기 불일치 처리는 잘라내기/빈 영역 채우기다.
  우리의 원본 비율·전체 화면 보존 정책으로 그대로 가져오면 안 된다.
- GPU adapter 일치, stride, texture 교체, 중지 시점, 재시작과 캡처 제외를 검증해야 한다.

Windows/NVIDIA 전용 후보이며 Python/Rust/CUDA 결합과 패키징 호환성 확인이 필요하다.
실제 프레임별 비용 감소는 미측정이다.

### 2. iw3의 학습형 SBS 합성 — 최우선 품질 비교 후보

`row_flow_v3`는 깊이·시차·수렴점으로 역방향 sampling 위치를 예측한다.
`row_flow_v3_sym`은 예측한 이동을 좌우에 대칭 적용한다. `mlbw_l2/l4`는 여러 sampling
층과 가중치를 사용한다. 단순 역방향 warp와 학습형 모델은 다르다.
[모델 선택][i-stereo], [RowFlow 구현][i-row], [MLBW 구현][i-mlbw]

동일한 RGB와 동일한 깊이 결과를 고정해 현재 CUDA 합성, `row_flow_v3_sym`,
`row_flow_v3`, `mlbw_l2s` 순으로 작은 비교를 권한다. 목표는 물체 경계 늘어짐·잔상,
가려진 배경의 채움, 가는 물체·자막·HUD, 양안 불일치 개선 여부다.
시차 단위·실제 pixel displacement·수렴점·경계 처리를 맞춰야 한다.
README의 symmetric 방식 속도 설명은 iw3 모델 간 비교이며 우리 CUDA 합성 대비 가속 근거가 아니다.

학습형 합성은 추가 추론 비용과 VRAM을 쓰므로 속도 개선을 미리 약속할 수 없다.
공개 구현으로 품질 차이를 먼저 확인하고, 가치가 있을 때만 ONNX/TRT 변환을 검토한다.
모델 파일은 출처·revision·hash·해당 가중치 사용 조건을 확인해 별도 관리한다.

### 3. NVIDIA Video Frame Generation — 새로 검토할 가치가 큰 보간 후보

Veyra에는 DLSSG와 독립된 Maxine VFX SDK의 `VideoFrameGeneration` 구현이 있다.
두 영상 프레임을 입력받는 방식이어서 캡처 영상에 맞고, 외부 게임 motion/depth 입력을
만들어야 하는 DLSSG와 조건이 다르다. Veyra는 D3D12/CUDA 공유 buffer/fence,
비동기 worker와 제한된 출력 슬롯을 연결한다. [VFG 구현][v-vfg],
[Veyra의 자체 검증 기록][v-vfg-evidence]

공식 문서는 Windows x64 Ada/Blackwell, GPU 입력, 2–8배 또는 지정 시점 보간을 설명한다.
RTX 5090은 해당 하드웨어 범위다. 동일 크기의 이전/현재/결과 영상이 필요하며
출력 buffer는 다음 실행 전에 소비하거나 복사해야 한다. [NVIDIA VFG][nv-vfg]

DepthSBS에는 우선 2배만 검토한다. 7680×2160 통합 SBS의 실제 SDK 수용 여부와 비용은
이번 조사로 확정하지 못했다. 좌우를 분리하면 중앙 seam은 피할 수 있으나 같은 시점·cut·
설정을 사용해도 서로 다른 보간 오류가 생길 수 있다. 통합/분리 모두 양안 검사가 필요하다.
앞단 RGB만 보간해도 깊이를 해당 시점에 맞춰야 하므로 낮은 깊이 추론률 문제가 자동 해결되지는 않는다.

기존에 부적합했던 Streamline DLSSG adapter나 고정 1:2 NVOF 깊이 재사용의 결과를
이 VFG 후보에 그대로 적용할 이유는 없다. 반대로 Veyra의 단안 4K 검증은 우리의 SBS 검증이 아니다.
공식 RTX 5090 1.90ms 수치는 1280×720 Medium 2배 조건이며 4K/Full SBS 비용이 아니다.
[공식 성능 조건][nv-perf]

실행 가능성 확인은 공식 SDK Core와 feature/model 확보부터 시작한다.
현재 공식 설치 절차에는 NGC 경로와 API key가 포함된다. 이번에는 접근·다운로드·설치를
시험하지 않았다. Python wrapper의 DLPack 출력도 SDK 소유 메모리이며 stream 제한이 있다.
제품 통합 시에는 기존 native CUDA 출력 경계와 C API 연결을 함께 검토한다.
[설치][nv-install], [Python API][nv-python]

현재 Base 4K native 8.43fps에 2배만 적용하면 산술상 약 16.9fps 수준이다.
보간 자체의 추가 비용까지 고려하면 안정적인 base30 확보를 대체할 수 없다.

### 4. Veyra의 출력 시간·큐 관리 — 조건부 채택

`LivePresentationTiming.h`는 source PTS, callback 시각, 보간 pair의 시간 간격과
출력 기준 시각을 구분한다. FG 없는 캡처는 준비 즉시 출력하고, FG pair에는
도착 jitter/drift 보정 및 늦은 생성 프레임의 유효시간을 사용한다.
`LivePairLatency.h`는 최근 준비 지연으로 대기 시간을 조절한다.
[시간 정책][v-timing], [pair 지연][v-latency]

우리의 단순 30/60Hz deadline과 polling에 비해 참고할 부분이 있지만, 이미 큐가
쌓이지 않는 구조이므로 이식만으로 처리량이 늘지는 않는다. 추론이 느린 상황과
출력 간격이 고르지 않은 상황을 나눠야 한다. 이후 base30→60 VFG 또는 더 빠른 입력을
시험할 때 59.94/60, 반복·누락, P95/P99 간격, callback→제출 시간을 측정할 후보다.
Veyra의 대기 상수나 Reflex 설정을 우리 경로에 그대로 적용하지 않는다.
물리 표시 지연은 별도 측정이다.

### 5. 자동 수렴점과 깊이 경계 보정 — 품질 비교 후 자동화

iw3의 `ConvergenceEstimator`는 작은 saliency 모델과 대상 깊이 분포를 사용해
수렴점을 계산하고 EMA/reset을 제공한다. 고정 수렴점인 현재 정책과 비교하면
주요 피사체를 보기 편한 위치에 두는 후보가 된다. [수렴점 구현][i-convergence]

기본 화면에 추가 슬라이더를 늘리지 않고 내부의 선택 가능한 실험 정책으로 시작한다.
얼굴·자막 사이에서 대상이 바뀌거나 카메라가 움직일 때 화면이 앞뒤로 출렁이는지 확인한다.
화면 가장자리 보존과 깊이 edge dilation/DepthAA도 각각 비교하되, 기존 guided filter와
보수적 coverage 위에 모두 중복 적용하지 않는다. [DepthAA][i-aa]

### 6. 중복 프레임 판별 — WGC에 느슨한 임계값을 바로 적용하지 않음

Veyra는 마지막으로 받아들인 새 화면을 기준으로 전체 픽셀을 비교한다.
축소 샘플만 비교해 작은 움직임을 놓쳤던 사례를 기록하고, 캡처 카드의 미세한 노이즈를
허용하는 band/outlier 방식으로 수정했다. [픽셀 비교][v-picture], [내용 cadence][v-dedup]

우리 Performance에도 정확한 RGB 일치 기반 깊이 재사용이 있으나 Base는 매 처리 프레임을
추론한다. 동일 프레임에 대한 GPU 단계별 재사용·절전은 검토할 만하다. 다만 캡처 카드에
맞춘 노이즈 허용값을 WGC에 복사하면 작은 커서·문자·HUD 변화가 무시될 수 있다.
우선 정확 일치 판정의 비용과 이득을 측정하고, 영상은 유지한 채 깊이만 재사용할지
완성 SBS까지 재사용할지 분리해야 한다. stateful 모델의 시간 간격/reset도 함께 다룬다.

### 7. inpainting, 투명 영상과 AR — 파일 기능/별도 확장 후보

master의 이미지·영상 inpainting은 가려진 배경을 채우는 품질 후보다.
영상 모델 경로는 frame queue와 앞뒤 padding이 있으므로 실시간 지연 없는 개선이라고
볼 수 없다. 우선 Offline Quality에서 빈 영역·시간 일관성을 평가하는 편이 적합하다.
[inpainting 구현][i-inpaint]

dev의 핵심 변화는 RGBA 영상, VP9/WebM·FFV1 투명 출력, RGB/alpha 지연 정렬,
depth+mask 인터페이스, WebXR AR passthrough와 chroma key다.
현재의 SDR 화면 캡처 SBS 목적에는 우선순위가 낮지만 배경을 제거한 입체 인물이나
MR 영상 파일을 만들 때 확장 가치가 있다. 디스플레이 게임 passthrough와
WebXR의 실제 공간 passthrough는 서로 다른 기능이다. [dev 차이][i-compare]

dev의 `--fit-window`는 소스 비율을 보존하는 fit이 아니라 창 전체로 늘리는 분기다.
요청한 원본 비율 보존의 기본값으로는 채택하지 않는다.
사용자 정의 depth Python 파일 자동 로딩도 현행 검증된 artifact 로딩 정책에 바로 넣지 않는다.
브라우저 스트리밍·iw3-player는 별도 시청 경로이며 기존 SBS 출력의 교체가 아니다.

## UX와 통합 범위

Veyra 자체도 Qt/QML 제어부와 native D3D12 영상 출력이 분리되어 있다.
따라서 참고할 처리 기능을 얻기 위해 DepthSBS를 WinUI로 전면 이식할 근거는 없다.
이미 있는 작은 제어창·별도 SBS 출력은 유지하고 새 실험은 개발 경로에서 검증한다.
품질을 확인한 뒤에만 기존 품질 선택이나 최소한의 자동 정책으로 노출한다.
[Veyra 구조 설명][v-readme]

Veyra의 노드 편집기, 다층 NR, 색보정, 콘솔 스트리밍·입력 전달은 지금의 최소 조작 흐름에
비해 범위가 크다. NR/SR을 좌우 눈에 각각 적용하면 서로 다른 디테일을 만들 가능성도
있으므로 기본 효과로 더하지 않는다. 출력 캡처 허용·OBS 호환·캡처 경계 제거는 과거에
제거한 외부 디스플레이 옵션을 되살리는 일이므로 이번 조사에서 제품 변경으로 제안하지 않는다.

## 설치·라이선스·배포 조건

| 대상 | 확인한 조건 | DepthSBS 적용 방식 |
|---|---|---|
| Veyra 앱 | Windows 11 x64, D3D12. C++20/MSVC2022, Qt 6.8.3 빌드 기록. proprietary SDK/런타임/모델은 Git에 없음 | 소스 복제만으로 동일 제품을 재현할 수 있다고 보지 않음. 전체 앱보다 기능별 참고 |
| Veyra 원본 코드 | 현재 GPL-3.0. Chiaki 결합 부분은 AGPL-3.0 및 예외 등 별도 조건 | 직접 코드 편입은 해당 파일·의존 closure와 배포 라이선스를 먼저 확인. 아이디어 자체의 독립 구현과 구분 |
| iw3/nunif, wc_cuda | 저장소 코드 MIT. iw3 배포에는 PyAV wheel의 FFmpeg GPL 조합 문제가 별도 기록됨 | MIT 고지 유지. 전체 환경 번들보다 필요한 모듈·모델별 검토 |
| depth/합성 가중치 | 코드 라이선스와 별개. DA2 Base/Large, 일부 VDA·Ultimate DAV2 등 NC 가중치 존재 | 기존 Base 사용이 상업 배포 허가를 뜻하지 않음. 모델별 원출처와 사용 조건 확인 |
| NVIDIA VFG/DLSS/NR | 공개 sample과 proprietary runtime/model 조건이 다름 | 공식 취득·지원 GPU·재배포 조건 확인. Veyra의 커뮤니티 DLL을 통째로 재사용하지 않음 |

근거: [Veyra notices][v-notices], [빌드 조건][v-build], [nunif MIT][i-license],
[nunif 배포 주의][i-license-note], [iw3 모델별 조건][i-readme], [wc_cuda][wc].
위 표는 저장소 조건 확인이며 특정 배포의 법률 검토 완료를 뜻하지 않는다.

## 권하는 작은 실험 순서

| 순서 | 실험 | 판단에 필요한 결과 |
|---|---|---|
| 1 | Base GPU 전처리, 이후 GPU 캡처 연결 | 기존 입력·깊이·SBS 비교 기준, 단계별 비용, 1080p/4K·세로·울트라와이드, resize/stop/source loss 검증 |
| 2 | 고정 RGB/depth를 사용한 합성기 비교 | 현재 CUDA vs RowFlow symmetric/일반 vs MLBW small. 양안 경계·HUD·움직임, 처리 비용·VRAM 비교 |
| 3 | 공식 VFG 2배 독립 probe | SDK/모델 접근, 7680×2160 수용 여부, 양안 동시점·cut·buffer 수명, GPU 경쟁·실제 base/final rate와 지연 |
| 4 | 유망 경로에만 출력 cadence·자동 수렴점 연결 | 59.94/60 pacing, 변동 부하, 깊이 출렁임, 같은 조건의 게임/영상·HMD 비교 |

합성 품질과 입력 최적화는 독립적으로 조사할 수 있다. 낮은 FPS를 높은 배수의 FG로
표시만 늘려 감추지 않고 fresh depth/base SBS/generated/presented를 나눠 기록한다.
이번 결과로 새 모델·FG·native 출력 기본값을 승격하지 않았다.

[v-branches]: https://api.github.com/repos/Likely7/Veyra-NRVideo/branches?per_page=100
[v-build]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/docs/BUILD_2.1.2.md
[v-readme]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/README.md
[v-capture]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/src/source/ScreenCaptureSource.cpp
[v-vfg]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/src/pipeline/VfgBackend.cpp
[v-vfg-evidence]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/docs/history/reports/VFG_INTEGRATION_ACCEPTANCE_2026-10-03.md
[v-timing]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/include/veyra/engine/LivePresentationTiming.h
[v-latency]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/include/veyra/engine/LivePairLatency.h
[v-picture]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/include/veyra/pipeline/PictureCompare.h
[v-dedup]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/include/veyra/engine/ContentDedup.h
[v-notices]: https://github.com/Likely7/Veyra-NRVideo/blob/fedd7fc29b9adbc13defd13d0c718a9db3d128ed/THIRD_PARTY_NOTICES.md
[i-branches]: https://api.github.com/repos/nagadomi/nunif/branches?per_page=100
[i-compare]: https://github.com/nagadomi/nunif/compare/0d3d92c8f4396da564c44524b6390ee5c76b9668...448e57962f49233432aac638996395f233d8d9cc
[i-readme]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/README.md
[i-capture]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/desktop/screenshot_thread_cuda.py
[i-stereo]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/stereo_model_factory.py
[i-row]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/models/row_flow_v3.py
[i-mlbw]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/models/mlbw.py
[i-convergence]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/convergence_estimator.py
[i-aa]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/models/depth_aa.py
[i-inpaint]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/base_inpaint.py
[i-license]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/LICENSE
[i-license-note]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/README.md#license-notes
[wc]: https://github.com/nagadomi/wc_cuda
[nv-vfg]: https://docs.nvidia.com/maxine/vfx/latest/Filters/VideoFrameGeneration.html
[nv-perf]: https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/PerformanceReference.html
[nv-install]: https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/InstalltheVFXSDK.html
[nv-python]: https://docs.nvidia.com/maxine/vfx-python/latest/api.html
