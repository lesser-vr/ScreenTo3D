# ZipDepth 추가 검토

검토일: 2026-11-06. 공식 논문·저장소 소스와 현재 DepthSBS 연결 지점을
읽은 결과다. 모델 다운로드, 추론, ONNX 변환, TensorRT 빌드, 실제 SBS 측정은
수행하지 않았다. 앱 코드와 기본 모델은 변경하지 않았다.

## 판단

**경량·저지연 후보로 비교 실험할 가치는 높다. 화질 개선이나 DA2 Small의
기본 대체 모델로 바로 채택할 근거는 부족하다.** 특히 사용자가 지적한 일렁임은
이 모델 자체가 해결하는 문제가 아니다. 먼저 VFG 없이 기존 Small과 비교한다.

## 공식 자료에서 확인한 내용

- 공개 GPU 체크포인트는 `zipdepth_base.pth`, 모바일용은
  `zipdepth_base_npu.pth`다. 여기서 Base는 ZipDepth 내부 이름이며 DA2 Base와
  같은 크기 등급이 아니다. 공개 README는 융합 후 약 6.1M 파라미터를 명시한다.
  코드에 small/large 설정도 있지만 공개된 학습 가중치와 혼동하면 안 된다.
  [공식 저장소](https://github.com/fabiotosi92/ZipDepth),
  [체크포인트 목록](https://github.com/fabiotosi92/ZipDepth/tree/main/checkpoints).
- 공식 페이지의 RTX 3090 TensorRT FP16 수치는 **384×384, 200회 forward의
  중앙 지연 약 0.8ms / 1,317FPS**다. 캡처·입체화·4K 출력까지 포함한
  DepthSBS 성능이 아니다. 출력은 상대 역깊이이며 미터 단위가 아니다.
  [공식 프로젝트](https://zipdepth.github.io/).
- 논문 표 2의 AbsRel은 아래와 같다. 낮을수록 좋으며 논문 평가 조건의
  정지영상 지표다. DA2 Small보다 다섯 데이터셋 모두 오차가 크다.

  | 모델 | NYUv2 | KITTI | ETH3D | ScanNet | DIODE |
  |---|---:|---:|---:|---:|---:|
  | DA2 Small | 6.1 | 8.4 | 6.3 | 5.2 | 21.4 |
  | ZipDepth | 8.4 | 12.3 | 10.0 | 8.8 | 22.6 |

  저자는 단일 이미지 모델의 프레임 간 일관성 부재와 temporal flickering을
  한계로 명시한다. 표의 우열이 실제 SBS 시각 품질을 그대로 결정하지는 않는다.
  [논문 표 2 및 한계](https://arxiv.org/html/2607.08771v1).

## Windows 및 연결 비용

Windows 적용 가능성은 높다는 **소스 기반 판단**이다. 이 검토에서 실행을
검증한 것은 아니다. 공식 구현은 PyTorch 연산이며 ONNX 정적 크기 내보내기를
제공한다. GPU용 체크포인트로 먼저 시작하고 NPU 변형은 초기 범위에서 제외한다.

1. **환경을 분리한다.** README의 PyTorch 최소 버전 설명과 실제 requirements의
   `torch>=2.12.0`, `torchvision>=0.27.0`이 다르다. 학습용 패키지도 포함하므로
   현재 앱 환경에 전체 requirements를 그대로 설치하지 않는다.
   [requirements](https://github.com/fabiotosi92/ZipDepth/blob/main/requirements.txt).
2. **전용 입력 처리가 필요하다.** 공식 predictor는 선형 리사이즈, BGR→RGB,
   0–1 변환을 사용한다. DA2 입력 경로를 그대로 쓸 수 없다. 짧은 변 384와
   32 배수 반올림을 사용해 16:9는 672×384가 된다. 원본 비율을 정확히 유지할
   제품 경로에서는 비율 유지 리사이즈+패딩/역변환을 별도로 검증한다.
   예: 704×384 고정 캔버스, 필요시 928×512 비교. 공식 입력 방식과의 차이는
   의도적인 전처리 변경으로 기록한다.
   [predictor](https://github.com/fabiotosi92/ZipDepth/blob/main/zipdepth/inference/predictor.py).
3. **변환 성공만으로 동등성을 인정하지 않는다.** 공식 export는 Conv/BN 융합과
   고정 크기용 pooling/cross-scale forward 치환을 한다. 원본 PyTorch→융합→
   ONNX→TensorRT FP16의 출력 오차를 순서대로 확인한다. 공식 로더는 missing
   keys를 경고만 하므로 제품용 검증은 필요한 가중치 누락을 실패 처리해야 한다.
   [export](https://github.com/fabiotosi92/ZipDepth/blob/main/scripts/export.py).
4. **현재 공통 경로를 재사용한다.** `live_model.py`의 어댑터,
   `live_backend.py`의 바인딩, `depth_backend.py`의 larger-is-nearer 계약에
   맞춘 별도 엔진을 추가하는 방식이 적합하다. GPU 캡처 입력부터 GPU 깊이 출력까지
   유지하고 공식 predictor의 CPU numpy 반환을 실시간 경로에 그대로 넣지 않는다.
   원본 비율, 깊이 범위 안정화, 움직임 이력 보정, 윤곽·배경 채움, 네이티브 출력은
   재사용하되 깊이 분포가 달라지므로 품질 검증은 새로 한다.
5. **VFG는 후속 단계다.** 현재 `vfg_runtime.py`와 `vfg_renderer.py`는
   DA2 Small/Base만 허용하며 렌더러 레이아웃도 검증한다. ZipDepth 등록만으로
   VFG가 작동하지 않는다. 별도 연결·수명·타임스탬프 검증 후 지원을 확장한다.

## 라이선스와 배포

저장소 LICENSE는 MIT이며 저작권·허가문 보존 조건을 명시한다.
체크포인트는 같은 저장소에 있지만, 확인한 자료에서는 가중치에 대한 별도
라이선스 설명을 찾지 못했다.
[공식 LICENSE](https://github.com/fabiotosi92/ZipDepth/blob/main/LICENSE).

논문은 DA2 Large를 교사로 사용한 증류를 명시한다. DA2 공식 문서에서 Large
가중치는 CC-BY-NC-4.0이다. 이것만으로 ZipDepth에 같은 제한이 자동 전파된다고
판정할 수는 없지만, 상업 배포 시 체크포인트 허가 범위와 학습 출처 조건을
확인할 쟁점으로 남긴다. MIT 저장소 표시만으로 모든 배포 조건이 해결됐다고
보고하지 않는다. 로컬 실험 판단과 제품 동봉 판단을 분리한다.
[DA2 라이선스](https://github.com/DepthAnything/Depth-Anything-V2#license).

## 권장 비교 실험

- 소스 revision 및 가중치 hash를 고정하고 `weights_only=True`로 구조를 검증한다.
- GPU용 Base의 PyTorch FP32를 기준으로 FP16/TRT 오차를 확인한다.
  먼저 고정 입력 하나로 시작해 변환·입출력 계약을 확인한다.
- 같은 공개 영상, 입체감 0.25, 동일 시간 안정화·윤곽 보정·출력 설정으로
  DA2 Small FP16과 비교한다. VFG는 끈다. 모델만 바뀐 비교를 먼저 확보한다.
- 3840×2160 입력→7680×2160 Full SBS에서 원본 처리 FPS, 출력 FPS,
  프레임 간격 P95, source age, GPU 메모리 및 단계별 시간을 측정한다.
  추론이 빨라도 캡처·4K 입체화 비용이 지배하면 전체 이득은 작을 수 있다.
- 이동·정지·장면 전환에서 움직임 정렬 잔차, 깊이 범위 흔들림, 얇은 윤곽,
  배경 노출 오류를 본다. 과도한 평탄화로 잔차만 낮아진 경우를 구별한다.
  마지막으로 실제 Owl3D 양안 품질·피로도를 확인한다.
- 실제 전체 처리 이득과 수용 가능한 품질이 확인되면 실험 선택지로 추가한다.
  기본 모델 승격이나 VFG 결합은 그 결과를 보고 결정한다.

이번 변경은 이 검토 문서뿐이다. 로컬 추론 결과나 Windows 지원 인증은 없다.
