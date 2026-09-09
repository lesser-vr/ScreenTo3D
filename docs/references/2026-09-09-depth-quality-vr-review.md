# 경량 깊이 모델·프레임 보간·VR 품질 검토

검토일: 2026-09-09. 사용자 요청에 따른 코드·공개 자료 검토 기록이다.
새 모델 실행, FG 연동, HMD 시험을 수행한 결과가 아니다.
제품 목표는 [PRODUCT](../PRODUCT.md#goal), 구현·측정 현황은
[implementation status](../implementation-status.md), 실행 우선순위는
[ROADMAP](../ROADMAP.md)가 각각 소유한다. 이 문서는 검토 당시 근거와
후보의 장단점을 보존하며 새로운 작업 규칙이나 지원 보증을 만들지 않는다.

## 결론

검토 대상은 DA2 Small보다 좋은 최종 입체 품질과 4K-per-eye 최종 60fps의
양립이다. 비교 기준은 사용자의 DA2 Small + Lossless Scaling FG이며,
입력 3840×2160, 각 눈 3840×2160, Full SBS 7680×2160을 구분한다.
모델 추론 60Hz 자체가 필수인 것은 아니다.

- 경량 대체 모델은 존재하지만 DA2 Small보다 VR 입체 영상 품질이 확실히
  좋다고 입증된 즉시 교체품은 이번 조사에서 확인하지 못했다.
- 먼저 Distill Any Depth Small을 같은 처리 조건에서 비교할 가치가 있다.
- 무거운 모델을 사용할 때는 원본 RGB 60fps를 보존하고 저주기 깊이를
  움직임에 맞춰 보정하는 구조가 유력한 연구 후보다. 깊이 20–30Hz는
  실험 목표이며 달성 수치가 아니다. 원본 자체가 저주기이면 이 이점은 없다.
- 완성 SBS의 30→60fps 보간은 비교 후보로 남긴다. 낮은 기본 FPS에 큰
  배수를 적용하는 것은 VR용 주 경로로 권하지 않는다.

## 경량 모델 후보

| 후보 | 근거와 기대효과 | 위험·미확인 사항 | 검토 판정 |
|---|---|---|---|
| Distill Any Depth Small | 24.8M, DA2 Small 구조. 기존 경로 재활용 가능성이 높음 | 배포된 DA2 Small과의 동일 조건 품질 우위, 변환 정확도와 실제 속도는 미확인 | 첫 교체 비교 후보 |
| Lightly `dinov2/dav3-relative-small` | 24.7M, DA3 Large 증류. ONNX·TensorRT export 제공 | ByteDance any-view DA3-Small과 다른 모델. 깊이 값 방향·sky 후처리·배포 라이선스 확인 필요. 동일 조건 DA2 Small 비교 부족 | 두 번째 교체 비교 후보 |
| DepthART-S/B | 6.0M/11.4M. 일부 데이터셋에서 DA2 Small보다 좋은 정확도와 낮은 실행 비용 | 데이터셋별 손익이 다름. Selective Scan CUDA/TRT 플러그인 및 Windows RTX 5090 경로 미검증 | 통합 비용이 큰 탐색 후보 |

Distill Any Depth 논문의 Small 증류 ablation은 배포된 DA2 Small 체크포인트와의
직접 비교가 아니다. Large 모델의 개선율도 Small의 개선율로 사용할 수 없다.

Lightly 공식 문서는 T4, FP16 TensorRT, 504×504에서 9.17ms를 보고한다.
이 값은 이 프로젝트의 RTX 5090, 전체 SBS 처리 시간이나 4K60 증거가 아니다.
DA2 relative는 큰 값이 가까움, DA3 relative는 큰 값이 멂으로 의미가 다르다.
LightlyTrain의 AGPL/commercial 조건과 가중치 사용 조건을 별도로 확인해야 한다.

DepthART 논문에서 DA2 Small 대비 S의 ETH3D δ1은 0.851→0.950이지만
NYU δ1은 0.973→0.964다. A6000 FP32의 native-setting forward 시간은
DA2 Small 13.06ms, DepthART-S/B 4.09/4.91ms이며 입력은 각각 518²/448²로
같지 않다. 정지영상 정확도·forward 속도는 양안/시간 품질을 입증하지 않는다.
ZipDepth는 조사한 논문의 정확도 및 flicker 한계상 이번 품질 향상 목적에서 후순위다.

근거: [Distill Any Depth 저장소](https://github.com/Westlake-AGI-Lab/Distill-Any-Depth),
[논문](https://arxiv.org/html/2502.19204v2),
[Small 체크포인트](https://huggingface.co/xingyang1/Distill-Any-Depth-Small-hf),
[Lightly 모델·export](https://docs.lightly.ai/train/0.17.0/depth_estimation.html),
[Lightly 라이선스 안내](https://docs.lightly.ai/train/0.17.0/licensing.html),
[DepthART 논문](https://arxiv.org/html/2607.17099v1),
[DepthART 배포 코드](https://github.com/xuefeng-cvr/DepthART/tree/main/deploy/pc),
[ZipDepth 논문](https://arxiv.org/html/2607.08771v1).

## 기존 DA2 Small의 개선 여지

1. **입력 종횡비:** 현재 518×518 입력 대신 높이×너비 392×700을 비교한다.
   패치 수는 1369→1400으로 약 2.3% 증가한다. 가로 정보와 비율을 보존하는
   대신 세로 샘플은 줄어든다. 품질 향상이나 동일 실행 시간은 가설이다.
   518×924는 별도 고비용 후보로 픽셀/토큰 수가 약 78.4% 증가한다.
2. **시간 안정화:** 같은 좌표의 EMA 강화보다 운동 보상 이력과 신뢰도·가림
   검출을 결합한다. flow 오류, 추가 GPU 비용, 잔상과 깊이 지연을 함께 비교한다.
3. **경계·가림:** 기존 guide, fractional splat 보정, hole filling은 이미 있다.
   검증된 과거 배경 재사용과 양안 일관된 실패 처리를 개선 대상으로 삼는다.
   필터가 잘못된 의미적 깊이나 보이지 않은 배경을 정확히 복원하는 것은 아니다.

코드 근거: [입력 처리](../../v1/depthsbs_app/live_gpu_candidate.py),
[TRT 입력 계약](../../v1/depthsbs_app/trt_backend.py),
[CUDA 깊이 처리](../../experiments/cuda_projection/live_depth.cu),
[스테레오 처리](../../v1/depthsbs_app/stereo.py).
공식 DA2는 [종횡비 유지 전처리](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/depth_anything_v2/dpt.py)를 사용한다.

## 무거운 모델의 속도 해석 정정

기존 답변의 “VDA depth 약 63ms이므로 모델 자체 상한이 약 15.8fps” 해석은
철회한다. depth 측정에는 CPU 전처리, 추론/캐시, 원본 크기 확대, 검증·동기화가
포함된다. 특히 VDA는 4K 전체를 float로 변환한 뒤 축소하므로 고정된 엔진
입력 크기만으로 전체 시간의 병목을 설명할 수 없다.

또한 현재 live worker는 캡처 sequence가 건너뛰면 모델·스테레오 이력을
reset한다. 의도적으로 낮은 주기로 처리할 때도 이력이 반복 초기화될 가능성이
있다. 이를 무조건 제거해서는 안 되며 실제 불연속과 의도적 샘플링을 구분하고
각 stateful 모델의 지원 간격을 검증해야 한다.

근거: [VDA 전처리](../../v1/depthsbs_app/vda_preprocess.py),
[device 경로](../../v1/depthsbs_app/vda_device.py),
[live reset](../../v1/depthsbs_app/live_sbs.py).
측정값의 최신 소유자는 [implementation status](../implementation-status.md)다.

## VR 보간과 PureDark AFW

PureDark UEVR의 AFW 브랜치(`fc8de1026622d42d0d1f76c3e9c8bb0d80b11035`)
인터페이스는 색·깊이·모션 벡터, 눈별 카메라 행렬과 UI 정보를 사용한다.
이는 RGB 두 장만 사용하는 일반 영상 보간과 다르다. DepthSBS의 일반 캡처에는
정확한 엔진 깊이·모션·카메라 데이터가 없으므로 같은 효과를 기대할 수 없다.
또한 DepthSBS는 이미 한 장의 RGB/깊이에서 두 눈을 만들기 때문에 게임의
두 번 렌더링을 줄이는 AFW의 성능 이득이 그대로 이전되지 않는다.

공개된 `PDAFWPlugin.cpp`는 빈 구현이며 핵심 워핑은 별도 DLL이다.
저장소 LICENSE도 All rights reserved이므로 공개 열람과 자유로운 재사용을
혼동하지 않는다. 이번 판단은 **설계 참고 대상이지 즉시 이식 가능한 구현이
아니다**라는 것이다. 공식 릴리스도 잔상 보정, 손·무기 이중상과 게임별 수정을
다루므로 무오류 해법으로 취급할 수 없다.

근거: [AFW 인터페이스](https://github.com/PureDark/UEVR/blob/fc8de1026622d42d0d1f76c3e9c8bb0d80b11035/dependencies/pd-afwmod/include/PDAFWPlugin.h),
[빈 구현](https://github.com/PureDark/UEVR/blob/fc8de1026622d42d0d1f76c3e9c8bb0d80b11035/dependencies/pd-afwmod/dummy/PDAFWPlugin.cpp),
[LICENSE](https://github.com/PureDark/UEVR/blob/fc8de1026622d42d0d1f76c3e9c8bb0d80b11035/LICENSE),
[공식 릴리스](https://github.com/PureDark/UEVR/releases).

### DepthSBS에 적용할 수 있는 설계 가설

- 원본 RGB 60Hz를 유지하고, 저주기 고품질 깊이를 현재 RGB 시점으로 운동
  보상한 뒤 공통 상태에서 두 눈을 생성한다. 두 눈을 독립적인 FG 큐에 넣지 않는다.
- 동일 source timestamp, 보간 계수, 컷/reset 및 대응하는 가림·신뢰도 판단을
  적용한다. 공통 판단을 쓴다는 것이 공통 깊이 오류까지 없앤다는 뜻은 아니다.
- flow 불일치, 새로 드러난 영역, 얇은 경계, 투명 물체, 오래된 깊이는 재사용을
  제한한다. 필요 시 새 깊이를 계산하거나 입체 강도를 양안에서 함께 완만히
  낮춘다. fallback 빈도와 깊이 pumping도 품질 손실로 측정한다.
- 깊이의 나이는 완료 시각이 아니라 원본 timestamp에서 측정한다. 비동기화가
  GPU 비용이나 추론 지연을 없애지는 않는다. 큐와 이력은 유한하게 유지한다.
- 소유한 HUD·자막은 보간 이후 합성한다. 캡처에 이미 합쳐진 HUD의 완전한
  분리는 보장하지 않는다.

영상 60fps와 HMD 72/90/120Hz는 별개다. 가상 스크린 영상은 저주기로 갱신해도
뷰어의 머리 추적·표시는 HMD 주기를 유지할 수 있다. Timewarp는 머리 움직임을
보정하지만 영상 내부 물체의 잘못된 보간을 고치지 않는다. 완전한 6DoF 장면
재구성이나 native App Spacewarp 지원을 이 설계의 기존 기능으로 주장하지 않는다.

근거: [Meta compositor](https://developers.meta.com/horizon/essentials/the-compositor/),
[독립 콘텐츠 갱신](https://developers.meta.com/horizon/documentation/unity/unity-sample-compositor-layers/),
[Spacewarp 오류 사례](https://developers.meta.com/horizon/documentation/unreal/unreal-sample-app-spacewarp/).

## 외부 FG의 위치와 판별 실험

Lossless Scaling는 안정적인 실제 SBS 30→60fps, Fixed ×2, no-scaling 비교
후보로 남긴다. 낮은 기본 FPS에 큰 배수를 붙이는 것은 우선안이 아니다.
같은 GPU의 FG 비용으로 기본 FPS가 낮아질 수 있다. 7680×2160 보존, 양안
일관성, 지연과 실제 출력 경로는 별도 확인이 필요하다. 창이 화면에 맞춰
축소된 결과를 캡처한 것만으로 full-resolution 전달을 증명할 수 없다.

현재 출력창은 캡처 제외 대상이므로 외부 FG 연동은 명시적인 전용 출력 선택과
자기 화면 재캡처 방지가 필요하다. 모든 창의 보호를 해제하는 방식은 아니다.
콘텐츠 FG와 뷰어의 장면 보간을 처음부터 중첩하지 않고 분리 비교한다.
기본 머리 재투영을 끄라는 의미는 아니다.

근거: [LS 공식 안내](https://steamcommunity.com/app/993090/allnews/),
[제품 설명](https://store.steampowered.com/app/993090/Lossless_Scaling/),
[캡처 제외 코드](../../v1/depthsbs_app/capture_sources.py),
[Windows 캡처 제외 API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity).

후보별 작은 판별 실험은 다음과 같다. 실행 순서와 작업 상태는 ROADMAP에만 둔다.

| 후보 | 유효성을 판별하는 비교 |
|---|---|
| 경량 모델 교체 | 같은 입력·precision·깊이 갱신 주기·후처리에서 DA2 Small과 비교. 경계/움직임/양안 개선 없이 비용만 증가하면 승격하지 않음 |
| 입력 종횡비 변경 | 가로 디테일 이득, 세로 디테일 손실, 순수 추론과 전체 시간 측정. 토큰 수만으로 속도 동등 판정 금지 |
| 깊이 운동 보상 | RGB60 유지 여부, depth age, 가림 오류·잔상·fallback 빈도, 컷 회복 비교. 반복 깊이보다 나쁜 오류나 지연이면 재설계 |
| 30→60 외부 FG | FG 켠 상태의 base FPS/p95, 실제 전체 해상도, 양안 시점·시차, 지연 비교. 숫자상 60만으로 통과하지 않음 |
| VR 품질 | 같은 화면 크기·거리·입체 강도에서 빠른 횡이동, 가까운 손/물체, 얇은 구조, 투명체, 자막과 컷을 HMD에서 비교 |

합성 정확도, 실제 GPU/미디어 실행, 모니터 영상 검토, HMD 검토, 장시간 성능은
서로 다른 증거다. 모델 추론·base SBS·생성 출력·물리 표시율을 따로 기록하며,
새로운 모델 이름이나 부드러운 단안 영상만으로 제품 목표 달성을 선언하지 않는다.
