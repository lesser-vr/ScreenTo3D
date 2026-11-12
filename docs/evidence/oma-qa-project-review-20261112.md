# ScreenTo3D — oh-my-agent / oma-qa review

검토일: 2026-11-12. **판정: FAIL / 검증 범위: partial**.
재현된 HIGH 2건과 MEDIUM 1건이 있다. 제품 코드는 수정하지 않았다.

## 설치와 적용 방식

- 원본: [first-fluke/oh-my-agent](https://github.com/first-fluke/oh-my-agent),
  CLI 소스 package 버전 20.42.3, 고정 커밋
  `ebf0d35ea2b9af35713cad000a0177da4fcfca82`.
- `%USERPROFILE%\.codex\skills`에 33개 `oma-*` 스킬과 필요한 `_shared` 참조를
  Codex skill-installer helper로 설치하고 파일별 SHA-256을 대조했다.
  기존 `_shared`의 TTS 관련 파일은 보존했다. MIT 라이선스를 포함한 349개 파일의
  해시 검증을 완료했다. 설치 기록: `out/oma-installation.json`.
- 이번 리뷰는 설치된 `oma-qa/SKILL.md`, execution-protocol, checklist의
  PREPARE → ACQUIRE → REASON → VERIFY → FINALIZE 절차를 적용한 **스킬 모드**다.
  OMA CLI 전체 설치·doctor·훅·외부 에이전트 dispatch를 실행한 것은 아니다.
  기존 프로젝트 `AGENTS.md`, Git 훅, 모델 설정, 메모리 서비스는 변경하지 않았다.
- 이 구성에는 OMA code-intelligence provider가 없다. 호스트 개발 지침에 따른
  로컬 `rg`·파일 읽기와 프로젝트 검증 도구를 사용했다. 도구 부재를 코드 결함으로
  취급하지 않았다. 새 스킬의 자동 탐색은 다음 턴부터 사용할 수 있다.

## 범위

현재 작업 트리와 미커밋 변경을 포함했다. 특히 다운로드/설치와 공개 모델 배포,
파일 변환·출력 게시·취소, GUI 큐/종료, 캡처 경계 및 작은 논리 화면의 접근성을
검토했다. 주요 읽기 범위는 `pipeline.py`, `desktop.py`, `desktop_jobs.py`,
`model_downloads.py`, `optional_models.py`, `download_cache.py`,
`official_sources.py`, `engine_cache.py`, `capture_sources.py`, `live_preview.py`,
`desktop_shutdown.py`, `qml/Main.qml` 및 관련 컨트롤·테스트·배포 스크립트다.

이것은 모든 native CUDA/C++ 커널의 전수 감사가 아니다. 신규 GPU 성능 벤치마크,
장시간 재생, 실제 Owl3D/VR 입체 화질, 다른 GPU·새 PC, NVDA 화면 읽기는 수행하지
않았다. 기존의 짧은 설치·변환 검증은 유효한 범위에서 재사용하되 이 누락 검증의
대체물로 보지 않았다. 웹 로그인·DB·브라우저 SLO 체크는 Windows 로컬 앱에 N/A다.

## P1 / HIGH — 짧은 오디오가 영상 뒷부분을 잘라도 성공 처리

**위치:** `v1/depthsbs_app/pipeline.py:466-470` (직접 원인: 469행).

최종 mux에 무조건 `-shortest`를 지정한다. 오디오가 영상보다 일찍 끝나면 이미
완성된 영상 트랙까지 잘린다. 앞선 `frames == decoded_frames` 검사는 mux 이전에
끝나고, 최종 파일은 존재·크기만 확인하므로 잘린 결과가 정상 완료로 게시된다.
원본은 보존되지만 결과의 상당 부분이 누락되며 사용자에게 실패가 전달되지 않는다.

실제 FFmpeg 9.0.1/NVENC 경로로 재현했다. 모델 추론만 고정 깊이 배열로 대체했고
디코드·SBS 합성·인코드·mux는 프로젝트 함수를 실행했다.

| 항목 | 입력 | 실제 출력 |
| --- | --- | --- |
| 영상 트랙 | 2.000초, 24fps, 48프레임 | 0.208333초, 5프레임 |
| 오디오 트랙 | 0.250초 | 0.250초 |
| 앱 완료 이벤트 | — | `complete`, 보고 프레임 48 |

**근거:** `out/oma-review-audio/report.json`.
재현 스크립트: `out/oma-review-reproduce-audio.py`.

**권고 수정:** 영상 종료 시점을 기준으로 mux한다. 오디오가 있는 경우 무음을
패딩한 뒤 `-shortest`를 쓰고, 무음 파일에는 오디오 필터를 추가하지 않는 방법이
가능하다. 다음은 기존 mux 인자에 대한 변경 예시이며 제품에는 적용하지 않았다.

```python
# 기존의 무조건 '-shortest'를 제거하고, 오디오가 있을 때만 추가한다.
if metadata['has_audio']:
    mux_arguments += ['-af', 'apad', '-shortest']
```

이 후보 인자를 독립 FFmpeg 명령으로 짧은/긴/없는 오디오 3조건에 적용해 모두
영상 48프레임·2.0초가 유지됨을 확인했다
(`out/oma-review-audio/proposed-remedy.json`). 전체 수정의 회귀 통과를 의미하지는
않는다. 최종 mux 이후 프레임 수/영상 길이도 검증해야 같은 유형의 성공 오표시를
탐지할 수 있다. 관련 ISO 품질 속성: 기능 적합성·신뢰성.

## P1 / HIGH — FFmpeg stderr 역압으로 파일 변환·취소 교착

**위치:** `v1/depthsbs_app/pipeline.py:323-326`, `214-219`, `448-450`.
취소 마커 작성: `v1/depthsbs_app/desktop.py:670-679`.

디코더의 stdout과 stderr를 모두 PIPE로 열지만 프레임 루프에서는 stdout만
읽는다. stderr는 프레임 루프가 끝난 뒤 읽는다. 손상 영상에서 오류 로그로
stderr 파이프가 차면 FFmpeg는 stderr 쓰기에서, worker는 다음 raw 프레임 읽기에서
서로 기다린다. `_read_frame()`에는 취소/대기 기한이 없어 UI가 마커를 작성해도
worker가 취소 검사를 다시 실행하지 못한다.

직접 생성한 600패킷 H264 MP4의 첫 패킷은 유지하고 이후 패킷의 NAL 길이를
손상시켰다. 실제 FFmpeg를 사용했고 모델만 고정 깊이로 대체했다. 취소 마커를
작성한 뒤 1.5초 내 반환하지 않았으며 디코더가 살아 있었다. **진단 코드가 별도로
stderr를 읽자** 총 236,612바이트가 배출되고 `InterruptedError`로 종료됐다.
따라서 단순히 느린 GPU 추론을 기다린 사례가 아니라 파이프 역압을 확인한 재현이다.

**근거:** `out/oma-review-pipe/report.json`.
재현 스크립트: `out/oma-review-reproduce-pipe.py`.
진단용 배출로 소유 프로세스를 정리했으며 제품에는 이 배출 코드를 넣지 않았다.

**권고 수정:** decode/encode stderr를 시작 즉시 독립적으로 배출하고, 보관하는
진단 꼬리는 제한한다. 다음은 배출 부분의 구현 예시다.

```python
from collections import deque
from threading import Thread

tail = deque(maxlen=16)  # 16 * 4096 = 최대 64 KiB의 오류 꼬리
def drain_errors(stream):
    while chunk := stream.read(4096):
        tail.append(chunk)

reader = Thread(target=drain_errors, args=(decode.stderr,))
reader.start()
```

이것만으로 일반적인 decoder/encoder hang까지 해결되지는 않는다. raw 읽기·쓰기와
mux에도 취소 가능한 대기, 소유한 child의 종료 기한을 추가하고 finally에서
child와 reader를 제한 시간 안에 종료·join해야 한다. 실제 수정 시 구현한 수명
정책을 함께 검증해야 한다. 로그 폭주/손상 입력에서 취소·창 닫기·임시 결과 보존을
확인하는 TC가 필요하다. 관련 품질 속성: 신뢰성·자원 사용의 제한.

## P2 / MEDIUM — 작은 논리 화면에서 변환 버튼이 화면 밖에 위치

**위치:** `v1/depthsbs_app/qml/Main.qml:35-43` (최소 높이: 41행),
하단 변환 액션: 284행.

파일 화면 전환 시 최소 높이 620과 선호 높이 740을 적용하지만 화면 작업 영역에
맞추지 않는다. 설정 영역 안쪽 스크롤과 달리 시작/취소 액션은 그 밖의 하단에
있다. 논리 화면 높이가 620보다 작으면 창 크기를 줄여 버튼을 화면 안으로 가져올
수 없다.

Windows Qt 앱의 **프로세스에만** scale factor를 적용해 실제 DPR 4.0,
작업 영역 960×522를 만들었다. 파일 창은 860×620이 되었고 변환 버튼의 아래쪽은
화면 좌표 y=600으로 작업 영역 하단 y=522를 벗어났다. OS 디스플레이 설정이나
사용자 설정은 변경하지 않았다. 초기 DPR 6.0 실험에서도 같은 현상을 관찰했지만
권고는 더 좁혀 확인한 DPR 4.0 결과를 근거로 한다.

**근거:** `out/oma-review-dpi-400/report.json`.
재현 스크립트: `out/oma-review-reproduce-dpi.py`.

**권고 수정:** 파일 탭 전환 때도 작업 영역을 기준으로 최소/현재 크기를 제한하고
내부 설정 영역만 스크롤되게 한다. 기존 `fit_rect`와 다음과 같은 window-side
최소 크기 계산을 연결할 수 있다.

```python
area = window.screen().availableGeometry()
frame = window.frameMargins()
usable_height = max(1, area.height() - frame.top() - frame.bottom())
window.setMinimumSize(QSize(min(760, area.width()), min(620, usable_height)))
```

실제로는 QML의 고정 최소값 재적용도 제거하고 현재 geometry까지 맞춰야 한다.
960×522 등 작은 작업 영역에서 탭 전환·키보드 탐색·하단 버튼의 도달 가능성을
검증하는 것이 필요하다. 관련 품질 속성: 사용성·접근성·호환성.

## 자동·런타임 검증과 남은 범위

`scripts/test-contracts.py --group cpu`는 **518 passed / 0 skipped**다
(`out/oma-review-contracts.json`). 이 결과와 위 결함은 모순이 아니다. 현재
pipeline 테스트는 subprocess·mux를 mock한 경우가 많아 최종 오디오 길이에 따른
실제 출력 프레임 누락과 OS pipe 용량의 역압을 검사하지 않는다. output placement
테스트도 주로 `fit_rect()`를 검사하며 파일 탭의 고정 최소 크기까지 확인하지 않는다.

| 검증 | 방법 | 관찰 | 판정 |
| --- | --- | --- | --- |
| 기존 CPU·Qt 계약 | 프로젝트 전체 CPU 그룹 | 518 통과 | PASS |
| 짧은 오디오 변환 | 실제 FFmpeg/NVENC, 고정 깊이 | 48 → 5프레임인데 성공 | FAIL |
| mux 수정 후보 | 독립 FFmpeg 3조건 | 모두 48프레임 보존 | 후보 인자만 PASS |
| 손상 입력 취소 | 실제 FFmpeg, 취소 마커, 진단 stderr 배출 | 역압·취소 대기 재현 | FAIL |
| 고배율 파일 화면 | 실제 Windows Qt, 프로세스 한정 DPR | 버튼 하단 y=600 > 522 | FAIL |
| 다른 GPU·장시간·물리 입체 화질 | 이번 리뷰에서 미실행 | 별도 검증 필요 | NOT ASSESSED |
| NVDA·완전한 키보드/스크린리더 감사 | 이번 리뷰에서 미실행 | 별도 검증 필요 | NOT ASSESSED |

우선순위는 **영상 보존 수정 → stderr 배출·취소 수명 보완 → 작은 화면 레이아웃**이다.
각 수정에 위 위험을 직접 검증하는 TC를 붙이고 final-media 검증까지 연결하는 것이
권장된다. 현재 결과는 수정 권고이며 수정 승인이나 출시 품질 인증을 뜻하지 않는다.
