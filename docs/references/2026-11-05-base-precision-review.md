# DA2 Base 반정밀도·양자화 적용 검토

2026-11-05. 현재 기본 Balanced/DA2 Base를 대상으로 코드, 기존 실험, NVIDIA
문서를 확인하고 제한된 실제 GPU 측정을 추가했다. RowFlow 직접 화질 비교는
사용자 요청대로 [백로그](../ROADMAP.md)에 남겼다. 이 검토는 기존 plan이나
앱 기본값을 교체하지 않는다.

## 결론

**교체는 가능하지만 파일만 바꾸거나 반정밀도 옵션을 켜는 작업은 아니다.**
현재 Base는 TensorRT FP32이며, 모델 엔진의 내부 연산만 낮은 정밀도로 바꾸고
입출력과 깊이 후처리는 FP32로 유지하는 접근이 가장 적합하다. Small 경로는 이미
FP16 모델 산출물을 사용하므로 Base와 같은 미적용 상태로 볼 수 없다.

권장 첫 후보는 **민감도에 따라 일부 연산을 FP32로 보존한 TensorRT FP16**이다.
그다음 대표 입력으로 보정한 INT8, 필요하면 FP8을 비교한다. BF16은 overflow에
유리하지만 항상 정확도가 높은 것은 아니며, 이번 표본에서는 FP16보다 오차가 컸다.
INT4/FP4는 현재 첫 후보로 삼을 근거가 부족하다.

| 후보 | 구현 가능성 및 필요한 작업 | 현재 판단 |
|---|---|---|
| 선택적 FP16 + TensorRT | FP32 ONNX의 민감 연산을 찾아 보존하고 나머지 변환, 프로파일별 새 plan 생성 | 첫 실험 후보. 기존 두 FP16 변환을 그대로 재사용하는 제안이 아님 |
| BF16 + TensorRT | BF16 지원 연산/캐스트와 parser 검증, FP32 I/O 유지 | 후보로 가능하나 이번 AMP 오차가 더 커 우선순위 낮음 |
| INT8 + TensorRT | 대표 입력으로 스케일 보정, Q/DQ 그래프 생성, 민감 연산 제외, 실제 INT8 커널 사용 확인 | 두 번째 후보. 현재 빌드/성능/품질 검증 없음 |
| FP8 + TensorRT | Q/DQ 및 ONNX opset 19 이상 등 내보내기 경로 확인 | INT8 이후 또는 병행 후보. RTX 하드웨어 지원만으로 앱 이득을 보장하지 않음 |
| INT4/FP4 | 연산 지원·가중치/활성값 형식·추가 오차와 캐스트 비용 검증 | 우선 보류. 작은 파일이 곧 낮은 지연을 뜻하지 않음 |

NVIDIA는 TensorRT 11.x에서 FP16/INT8 등의 builder flag와 기존 INT8 calibrator를
제거하고, 형식이 명시된 변환 그래프 또는 Q/DQ 그래프를 사용하도록 안내한다.
현재 설치된 11.2.1.2에 맞는 새 산출물이 필요하다.
[TensorRT 11 이전 가이드](https://docs.nvidia.com/deeplearning/tensorrt/latest/api/migration/tensorrt-10x-to-11x-python-api-patterns.html)

## 현재 코드에서 가능한 연결 방식

- `da2_base.py`는 518x896 / 518x924 FP32 입출력 서명, GPU/runtime 및 정확한
  plan 해시·크기를 검증한다. 외부 FP16/INT8 ONNX나 체크포인트를 다운로드해
  기존 `.plan` 대신 넣는 것으로 동작하지 않는다.
- **FP32 입력/출력을 유지하는 내부 혼합정밀도 엔진**이면 기존 GPU 전처리,
  패딩/크롭, source-size 업스케일, 깊이 소유권과 네이티브 SBS 출력 연결을
  유지할 수 있다. 엔진 검증·명시적 선택·진단에 실제 정밀도를 반영해야 한다.
- 반대로 입출력까지 FP16으로 바꾸면 전처리 버퍼와 TensorRT 바인딩,
  `Da2BaseDeviceDepth.validate()`의 FP32 계약도 바꿔야 한다. 첫 후보에서는
  이 경계 변경을 피하는 편이 비교가 명확하다.
- FP32 정규화·시간 안정화·가이드 필터와 CUDA SBS는 유지한다. 작은 모델 깊이
  맵의 정밀도 변경과 최종 4K 픽셀 처리 최적화는 서로 다른 비용이다.
- 16:9뿐 아니라 두 설치 프로파일과 세로·울트라와이드 패딩을 검증해야 한다.
  새 엔진은 별도 경로/해시로 보관하며 기존 검증된 FP32 plan은 유지한다.

## 재확인한 과거 결과

기존 FP16 변환과 FP32 encoder/FP16 head 변환은 각각 68개 비교 모두 유한한
결과를 냈지만, `atol=rtol=0.001` raw-depth 기준은 각각 0/68이었다. 최대 절대
차이는 각각 0.17643, 0.09163이었다. 따라서 과거 실패를 단순 overflow로
단정하거나, BF16이면 해결된다고 추론할 수 없다.

당시 짧은 파일 변환은 Base FP32 11.58fps에서 두 후보 각각 14.96 / 14.72fps로
빨라졌지만 기존 수치 기준은 통과하지 못했다. 이는 **과거 파일 파이프라인**의
측정이며 현재 네이티브 앱의 개선율이 아니다. 과거 후보에 대한 판정은
새 민감도 기반 변환 자체를 금지하지 않는다.
[원본 기록](../evidence/model-comparisons.md#record-result-model-evaluation-2026-09-05)

## 이번에 실행한 제한 측정

RTX 5090, Python 3.13.14, PyTorch 2.7.1+cu128, TensorRT 11.2.1.2.
같은 `(1,3,518,924)` GPU 입력과 CUDA stream을 사용하고 TF32를 껐다. 5회 준비
후 순서를 순환시켜 각 30회 CUDA event 시간을 측정했다. AMP 출력의 FP32
변환을 포함한다. Torch compile, 새 TensorRT 반정밀도 plan, INT8/FP8은 실행하지 않았다.

| 실행 | 모델 구간 중앙값 |
|---|---:|
| 현재 TensorRT FP32 | **23.37ms** |
| PyTorch FP32 | 42.70ms |
| PyTorch autocast FP16 | 24.28ms |
| PyTorch autocast BF16 | 25.10ms |

AMP는 PyTorch FP32보다 빠르지만 현재 TensorRT FP32보다 빠르지 않았다.
따라서 단순 PyTorch 반정밀도 교체의 속도 근거는 없다. 이 결과는 TensorRT
FP16/BF16의 속도를 예측하거나 반정밀도 TensorRT를 기각하는 결과가 아니다.

공개 영상 FloorballGame / OfficeWalk / ParkingGarage에서 각 12프레임,
검정·회색·흰색 상수 3개까지 총 39개 입력을 비교했다. 공식 고정 체크포인트와
소스 로더, 공개 fixture 해시 검증을 재사용했다. PyTorch FP32가 수치 기준이다.

| 후보 | 유한 결과 | 기존 raw-depth 기준 통과 | 공개 프레임 중 최대 평균 절대 차이 | 공개 프레임 중 최대 단일값 차이 |
|---|---:|---:|---:|---:|
| 현재 TensorRT FP32 | 39/39 | 39/39 | 0.00000523 | 0.000527 |
| AMP FP16 | 39/39 | 0/39 | 0.01195 | 0.67358 |
| AMP BF16 | 39/39 | 0/39 | 0.08077 | 2.34390 |

깊이는 상대값이므로 위 숫자는 미터 오차가 아니다. 평균 절대 차이를 기준 깊이의
2–98 백분위 범위로 나눈 값은 공개 프레임 중 최대 FP16 0.0742%, BF16 0.4835%였다.
이는 **일반 화질 손실률이나 최종 SBS 픽셀 오차가 아니다**. 경계와 시간축에서
차이가 집중될 수 있어 전체 SBS·안정성 검증 없이 시각적 동등성을 주장하지 않는다.

스크립트: `v1/probe_base_precision.py`.
결과: `out/base-precision-review-20261105/report.json`.
기존 TensorRT plan SHA-256:
`e5b17445993602abf2a01c0f6e7686d5fa67afec49bd9ef8bb4c133175c89d2e`.
측정 중 다른 GPU 벤치마크를 실행하지 않았고 앱 산출물을 변경하지 않았다.

BF16은 FP16보다 지수 범위가 크지만 유효 숫자 정밀도는 낮다. NVIDIA도 민감한
연산을 FP32로 보존하는 혼합정밀도를 안내한다. 이번 선택적 FP16 우선 제안은
그 일반 원리와 위 로컬 결과에 근거한 판단이다.
[NVIDIA 정확도 설명](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/accuracy-considerations.html)

## Windows 양자화 도구와 설치 경계

Model Optimizer의 Windows ONNX 경로에 INT8/FP8이 나열되어 있으나 TensorRT
배포 열은 실험 상태다. 이는 DA2 Base의 검증 완료를 뜻하지 않는다.
현재 앱 환경에 ModelOpt는 설치되어 있지 않다.
[Windows 지원 표](https://nvidia.github.io/Model-Optimizer/guides/0_support_matrix.html)

확인한 ModelOpt **main 소스**는 `torch>=2.10`을 요구한다. 이는 현재 앱의
2.7.1과 다르므로 기존 환경에 무조건 최신 패키지를 설치하지 않는다. 별도 변환
환경과 고정 버전을 정한 뒤 ONNX/plan만 검증하여 들여오는 구성이 적합하다.
main의 요구사항은 특정 배포 버전의 설치 검증을 대신하지 않는다.
[ModelOpt 의존성](https://raw.githubusercontent.com/NVIDIA/Model-Optimizer/main/pyproject.toml)

ModelOpt ONNX AutoCast는 FP32-FP16/BF16 변환, FP32 유지 노드 지정과 실제 입력
통계를 이용한 변환을 지원한다. 과거의 연산 종류 단위 제외보다 더 세밀한 후보를
만드는 도구가 될 수 있으나, 이번에는 설치하거나 실행하지 않았다.
[AutoCast 문서](https://nvidia.github.io/Model-Optimizer/guides/8_autocast.html)

INT8은 대표 입력으로 양자화 스케일을 정하고 **Q/DQ 형태**로 내보내야 한다.
CPU용 `QLinearConv`, `MatMulInteger` 형식 모델은 TensorRT로 바로 옮길 수 없다.
FP8 표준 Q/DQ는 opset 19 이상을 요구하므로 현재 opset 17 export를 그대로
사용한다고 가정하지 않는다. 실제 parser·커널·캐스트 비용을 확인해야 한다.
[TensorRT Q/DQ와 ONNX 지원](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/quantized-types-explicit-quantization.html)

검증된 원본 Base를 직접 변환하는 경로를 우선한다. 외부 양자화 파일은
전처리·깊이 방향·입출력 shape·형식·출처를 새로 확인해야 하며 기존 plan과 호환된다고
볼 수 없다. 정밀도를 낮춰도 Base 원본 가중치의 CC-BY-NC-4.0 조건은 사라지지 않는다.
[공식 Base 모델 카드](https://huggingface.co/depth-anything/Depth-Anything-V2-Base)

## 권장 후속 시험 범위

1. 같은 Base와 입력 해상도로 선택적 FP16 TensorRT 후보 하나를 만든다.
   정규화·softmax·민감 attention/깊이 출력 연산의 정밀도를 데이터로 결정한다.
2. 후보용 입력과 별도 평가 입력을 분리한다. 실제 영상·밝고 어두운 장면·글자/
   얇은 물체·단색·컷·다양한 화면 비율을 포함해 raw/정규화 깊이, 경계 순서,
   최종 좌우 RGB 차이와 시간축 변화량을 기록한다.
3. 기존 동작 보존을 주장하려면 기존 오차 계약을 유지한다. 양자화의 의도적
   품질 교환관계를 평가한다면 실험 전에 별도 수치/영상 비교 계약을 정한다.
   결과를 본 뒤 기준을 완화해 합격시키지 않는다.
4. 실제 네이티브 앱의 1080p/4K 처리·출력 fps, 지연, 메모리, 시작/크기변경/
   중지/재시작을 비교한다. 모델만 빨라져도 전체 출력 60fps가 보장되지는 않는다.
5. 이득이 남고 오차 원인이 제어되면 INT8 Q/DQ로 범위를 넓힌다. 직접 화질
   확인이 어려운 동안에도 이 객관적 시험은 가능하지만 시청 동등성은 미검증으로
   남긴다. 현재 기본 FP32를 교체했다는 결론은 이번 검토에 포함되지 않는다.
