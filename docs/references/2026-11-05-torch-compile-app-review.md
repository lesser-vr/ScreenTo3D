# DepthSBS 앱에 torch.compile 적용 검토

2026-11-05. 현재 코드의 연결부 검토와 제한된 실제 측정 결과다. 앱 구현·기본값
변경 승인이 아니라 적용 가능성과 이득을 판단하는 보고서이며, 현재 상태의 소유자는
[implementation-status](../implementation-status.md)다.

## 판단

**현재 앱을 빠르게 만들기 위한 일괄 적용은 권하지 않는다.** `torch.compile`은
PyTorch 모델/연산을 최적화한다. 현재 주된 Base 추론은 TensorRT, SBS 합성은
직접 작성한 CUDA이므로 이들에 스위치를 붙이면 추가로 빨라지는 구조가 아니다.
실제 Base FP32 대체 경로를 시험해도 현재 TensorRT보다 느렸다.

**iw3를 화질 개선용 합성기로 도입한다면 compile은 유효한 구성 요소다.** 다만
iw3 자체의 eager 대비 약 2배 이득을 DepthSBS 대비 약 2배 이득으로 해석하면 안 된다.
추가 통합 비용과 기존에 관찰한 얇은 물체/경계의 화질 교환관계도 남아 있다.

| 적용 대상 | 확인한 내용 | 권장 판단 |
|---|---|---|
| 기존 Base TensorRT | 직접 compile 대상이 아님. PyTorch 대체 후보를 동일 입력으로 측정 | 현재 TensorRT 유지 |
| 기존 CUDA SBS | 이미 네이티브 CUDA로 실행. Torch 모델 forward가 아님 | compile을 붙이기 위해 재작성하지 않음 |
| iw3 RowFlow v3 symmetric | 고정 해상도 compile 시 4K 합성 27.47→13.99ms | 화질 후보를 앱에 시험할 때 첫 후보 |
| iw3 RowFlow v3 / MLBW small | compile 후 4K 합성 각각 27.90 / 27.25ms | symmetric의 화질 부족을 보완할 근거가 있을 때 비교 |
| Base의 남은 Torch 후처리 | 기존 프로파일에서 upscale 약 0.05–0.19ms, finite-check wait 약 0.18–0.21ms | 전체 성능에 비해 이득 상한이 작아 우선순위 낮음 |

이 판단은 현재 FP32/default compile 및 측정한 후보에 한정된다. 다른 정밀도,
attention 구현, 컴파일 모드나 미래 버전의 가능성을 배제하지 않는다.

## 추가로 실행한 Base 비교

`v1/benchmark_base_compile.py`는 기존 검증된 Base 소스/가중치 로더를 재사용한다.
앱의 전처리로 만든 **같은 GPU 입력 `(1,3,518,924)`**를 세 실행 경로에 전달했다.
PyTorch는 FP32, AMP와 TF32를 끄고 `torch.compile(mode='default', dynamic=False)`를
사용했다. TensorRT는 앱의 기존 검증된 FP32 plan을 변경하지 않았다.

RTX 5090, PyTorch 2.7.1+cu128, Triton Windows 3.3.1.post21, TensorRT 11.2.1.2.
첫 컴파일 이후 5회 준비 실행, 경로 순서를 순환시키며 각 30회 측정했다.
동일 CUDA stream에서 입력→모델 출력의 CUDA event 시간을 측정한다.

| 경로 | 모델 GPU 시간 중앙값 | 해석 |
|---|---:|---|
| 현재 TensorRT | **25.00ms** | 이번 동시 설치/측정 조건의 기준 |
| PyTorch eager | 44.13ms | 일반 PyTorch 실행 |
| PyTorch + compile | **37.77ms** | eager보다 약 14.4% 짧지만 TensorRT보다 약 51% 오래 걸림 |

첫 컴파일·실행은 33.18초, 생성된 커널은 128개다. 공개 영상 3종의 raw model depth가
모두 유한한 값임을 확인했다. TensorRT 대비 compiled depth 평균 절대 차이는
약 2.43e-6~2.97e-6, 최대 차이는 3.24e-4였다. **정확히 같은 출력이 아니며**, 전체
SBS parity를 통과했다는 뜻은 아니다. 별도 허용 오차를 사후 설정해 합격시키지 않았다.

증거: `out/base-compile-review-20261105/report.json`, 인접 로그.
원본 Base 가중치와 TensorRT plan의 SHA-256은 보고서에 기록되어 있다.
Triton 의존성은 [앞선 compile 실험](../evidence/iw3-torch-compile-20261105.md)의
별도 폴더만 재사용했다. 앱 실행 환경과 패키지는 변경하지 않았다.

이 수치는 전처리·업스케일·캡처·SBS·GUI를 제외한 모델 시간이다. 다른 TensorRT
프로파일 518x896, AMP/FP16, `max-autotune`, 게임 경쟁 부하, 지속 실행은 새로
시험하지 않았다. 기존 단독 프로파일의 약 23ms와 이번 25ms를 성능 회귀로 해석하지
않는다. 이번 결론은 같은 실행 내 세 경로의 비교에 근거한다.

## iw3 통합에 필요한 변경

현재 `_post()`는 정규화·시간 안정화·가이드된 깊이를 CUDA DLL 내부에 보관한다.
Python에 넘기는 `aligned`는 진단/조건부 배경 보정용 CPU 배열이다. 단순히 여기에
iw3를 호출하면 깊이를 GPU→CPU→GPU로 왕복시킬 수 있다.

현재 `TextureOutputMixin._project()`의 `live_pool_publish()`는 기존 합성과
공유 텍스처 게시를 함께 수행한다. 외부 Torch의 좌우 RGB 텐서를 그대로 게시하는
일반 인터페이스는 없다. 필요한 작업은 다음과 같다.

1. 최종 깊이를 명확한 수명·소유권을 가진 GPU 텐서로 전달하는 연결부를 만든다.
   기존 배경 보정 결과와 깊이 방향, 시간 안정화가 유지되어야 한다.
2. 동일 engine stream에서 compiled iw3와 양안 warp를 실행한다. 이전 비교에서
   확인한 눈 순서 차이와 입체 강도 매핑을 유지하고, uint8 변환/색상 순서를 검증한다.
3. 외부 GPU RGB를 기존 네이티브 출력 풀에 게시하는 경계를 추가한다. 두 슬롯,
   소비자 사용 완료, 완료 전 메모리 유지, resize 시 세대 교체를 보존한다. 기존 host
   출력에도 동일한 눈/색상 결과를 전달해야 한다.

관련 파일: `live_gpu_candidate.py`, `live_source_gpu_candidate.py`,
`live_gpu_texture.py`, `live_texture_pool.py`, `live_sbs.py` 및 해당 CUDA DLL.
검토만으로 이 변경들을 구현하거나 검증했다고 주장하지 않는다.

현재 단독 프로파일의 4K **후처리+native SBS 전체 구간**은 약 6.93ms였다.
compiled symmetric의 **합성 구간만** 약 13.99ms다. 입력·측정 경계가 다른 실험이므로
정확한 배수 비교는 불가능하지만, 현재 경로를 교체하면 속도가 좋아진다는 근거는
없다. 화면 표시까지 포함한 앱 비교가 있어야 실제 이득을 판단할 수 있다.

## 사용자 경험과 운영 조건

- **compile 스위치는 기본 UI에 노출하지 않는 것이 적합하다.** 채택한 실행 경로가
  내부에서 설정을 결정하고, 기존 창 선택·SBS 시작/중지만 유지한다.
- cold compile 때 기존 상태 영역에 `처음 실행을 준비하고 있습니다`처럼 단계와
  취소 가능 상태를 표시한다. 준비가 끝나기 전 빈 창을 성공한 출력으로 취급하지 않는다.
  앞선 iw3 컴파일은 수초~수십 초, 이번 Base는 약 33초가 필요했다.
- iw3는 `dynamic=False`를 사용해 해상도별로 특화하는 후보가 적합하다.
  새 해상도에는 준비 시간이 생길 수 있다. 소스 크기를 계속 드래그하는 동안 새
  컴파일을 매번 생성하지 말고, 크기가 안정되면 한 번 준비한다. 원본 비율이나 최종
  출력 해상도를 컴파일 편의를 위해 몰래 바꾸지 않는다.
- 캐시는 모델·입력 shape·정밀도·Torch/Triton 버전·GPU를 구분하고, 용량과 동시
  준비 작업 수를 제한한다. 외부 미검증 캐시를 읽지 않고 실제 사용 여부를 진단에 남긴다.
- 현재 시작 대기는 120초, 중지 후 무응답 worker 종료는 5초다. 이를 늘리는 것만으로
  해결하지 말고 준비 단계와 heartbeat를 구분해야 한다. 컴파일 중 취소할 때 worker뿐
  아니라 자신이 시작한 컴파일러 자식 프로세스도 남지 않도록 관리하는 검증이 필요하다.
- 설치 준비·첫 실행·캐시 재사용·컴파일 실패를 구분한다. 기존 iw3 지원 확인은 실패 시
  eager 모델을 돌려줄 수 있으므로, 체크박스보다 실제 생성 커널/선택 경로를 검증해야
  한다. 사용자에게 알리지 않은 실행 경로 변경은 넣지 않는다.

PyTorch의 [compile 문서](https://docs.pytorch.org/docs/2.7/generated/torch.compile.html)는
기본 자동 shape 일반화, `dynamic=False`의 shape 특화, 재컴파일 제한과 eager 전환을
설명한다. 실제 우리 환경에서도 자동 shape 일반화의 4K 성능 저하와 고정 shape의
이득이 각각 관찰되었다. 컴파일 설정을 앱의 전체 생명주기와 함께 설계해야 하는 이유다.

## 권장하는 후속 범위

현재 TensorRT+CUDA를 유지한다. `torch.compile` 자체를 적용하는 일을 목표로 삼기보다,
**iw3의 대각선/경계 표현이 실사용 화질을 개선하는지**를 별도 후보로 판단한다.
그 후보를 앱에 시험한다면 우선 symmetric 하나만 GPU 연결부까지 붙이고 다음을
확인하는 범위가 적절하다.

- 동일 입력의 실제 처리/출력 fps, 지연, GPU 메모리와 cold/warm 시작 시간.
- 1080p·4K·세로·울트라와이드 크기 및 resize·중지·재시작·취소 시 자원 정리.
- 기존 합성과 compiled iw3의 글자·얇은 물체·가림·움직임, 이후 실제 양안 보기.

그 결과가 이득을 입증하기 전에는 기본 경로로 승격하지 않는 것을 권한다.
이번 검토에서는 앱 코드, GUI, 기존 실행 기본값을 바꾸지 않았다.
