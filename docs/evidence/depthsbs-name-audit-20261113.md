# 사용자 데이터 경로 변경 및 DepthSBS 이름 조사

2026-11-13. 로컬 구현·검증 결과이며 GitHub 릴리스는 교체하지 않았다.
제품 표시명은 **ScreenTo3D**, 이번에 요청한 사용자 데이터 폴더명은
**StereoTo3D**로 적용했다. 체크아웃 폴더 자체의 이름은 변경하지 않았다.

## 저장 경로와 이관

| 용도 | 새 경로 |
|---|---|
| 선택 모델·설치 런타임 및 GPU별 엔진 | `%LOCALAPPDATA%\StereoTo3D\models` |
| 검증된 다운로드·이어받기 캐시 | `%LOCALAPPDATA%\StereoTo3D\downloads` |
| DA2 Small 엔진 캐시 | `%LOCALAPPDATA%\StereoTo3D\engines` |
| EXE 실행 로그 | `%LOCALAPPDATA%\StereoTo3D\logs` |

`user_data.py`가 공통 루트를 소유한다. 단순 경로 조회는 파일을 옮기지 않으며,
데스크톱 시작 시 모델 조회 전에 기존 루트를 이관한다. 새 루트가 이미 있으면
누락된 항목만 잠금 안에서 옮긴다. 기존 새 파일을 덮어쓰지 않고 충돌한 옛 파일은
원래 위치에 남긴다. 비어 있는 옛 폴더만 제거한다. 링크·경로 이탈을 거부하고,
이관 실패는 번역 가능한 `E_DATA_MIGRATION`으로 전달한다.

이 PC의 실제 C: 사용자 데이터 **635개 파일 / 3,249,199,672바이트**를 옮겼으며
전체 파일의 크기·SHA-256이 이관 전과 일치했다. VDA 두 프로필의 보호된 영수증과
설치 판정이 유효했고 Base·VDA 모두 기존 설치로 인식했다. 모델을 다시 받거나
엔진을 재생성하지 않았다. 기존 데이터 안의 옛 이름 하위 항목은 내용 그대로
보존했다. 충돌이 있는 다른 PC에서는 보존된 옛 파일 때문에 이전 루트가 남을 수 있다.

개발용 Microsoft Store Python은 AppData를 개인 LocalCache와 합쳐 볼 수 있다.
초기 개발 인터프리터에서 본 650개 항목은 실제 배포 앱의 물리 폴더 수와 달랐다.
물리 부모가 다른 루트를 합치지 않도록 보완하고, 최종 이관·해시·모델 검증은
배포판의 비패키지 CPython에서 실행했다. 개발용 개인 캐시는 삭제하지 않았다.
이 동작은 [Python의 Windows 경로 리디렉션 설명](https://docs.python.org/3.13/using/windows.html#redirection-of-local-data-registry-and-temporary-paths)에 따른다.

## 이름 사용처 조사

이번 보고서와 상태 갱신 직전 스냅샷에서 `git ls-files --cached --others
--exclude-standard`로 수집한 883개 파일 중 UTF-8 텍스트 863개를 대소문자 구분 없이
검색했다. 콘텐츠에 **481개 파일 / 1,844개 행 / 1,914회**가 남아 있었다.
경로명 자체에 포함된 파일은 144개이며, 대부분 `v1/depthsbs_app/` 아래다.
무시된 `out/` 빌드 산출물과 Git 이력·외부 설치 폴더 전체는 이 집계에 포함하지 않았다.
아래 영역별 파일 수는 서로 겹치지 않는다. 문서에는 날짜가 붙은 검토 문서도 포함한다.

| 영역 | 파일 수 | 등장 횟수 |
|---|---:|---:|
| 앱 Python·QML | 26 | 65 |
| 네이티브·C++ 코어 | 8 | 31 |
| 테스트 | 159 | 651 |
| 스크립트·빌드·실험 및 기타 설정 | 224 | 978 |
| 현재 문서·검토 자료 | 21 | 73 |
| 과거 증거·릴리스 기록 | 43 | 116 |

| 남은 용도 | 대표 위치 | 판단 |
|---|---|---|
| 사용자 설정 저장소 | `desktop_preferences.py:12`, `desktop.py`의 application/organization name, `native/launcher/main.cpp:37` | `DepthSBS/DepthSBS` 레지스트리 유지. 언어·모델·출력 선택을 보존한다. 변경하려면 별도 설정 이관이 필요하다. 화면 표시명은 ScreenTo3D다. |
| Qt가 자동 생성하는 화면 캐시 | `%LOCALAPPDATA%\DepthSBS\DepthSBS\cache\qmlcache` 및 pipeline cache | 위 application/organization name으로 정해진다. 최종 EXE 실행 후 이 옛 루트가 다시 생김을 확인했다. 모델·TensorRT 엔진·다운로드의 저장 위치와는 별개이며 이번에는 유지했다. |
| Python 모듈·명령 | `v1/depthsbs_app/`, `v1/depthsbs.py`, `python -m depthsbs_app…` | 내부 import·작업자 진입점·빌더·시험이 연결되어 있다. 콘텐츠 등장 중 1,284회가 모듈명 포함 행이다. |
| 환경변수·빌드 옵션 | `DEPTHSBS_LAUNCH_LOG`, `DEPTHSBS_*` | 46개 고유 이름. 기존 실행기·측정 도구 호환성이 있으므로 일괄 치환보다 새 이름 별칭 후 이관이 적절하다. |
| 캡처·QML 프로토콜 | `capture_sources.py:22`의 `DepthSBS.OutputWindow.v1`, `qml/NativeFrame.qml:2`의 `DepthSBS.Native` | 출력 재캡처 방지와 네이티브 등록 양쪽이 공유한다. 생산자·소비자를 함께 검증해야 한다. |
| 내부 번들 경로 | `desktop_jobs.py:14`, `scripts/build-desktop-portable.py`의 `DepthSBS-GPU-Preview` | 패키징과 런타임 탐색이 공유하는 경로. 이번 사용자 데이터 루트와 별개다. |
| C++ 빌드·네임스페이스 | `CMakeLists.txt`, `include/depthsbs/`, `src/` | `depthsbs_core`, `depthsbs` CLI 및 API 이름. README의 capability/mode 명령도 실제 실행명이다. |
| 아이콘 파일명 | `assets/depthsbs.png`, `assets/depthsbs.ico`, `native/launcher/app.rc` | 파일명만 옛 이름이다. 작업표시줄 앱 ID와 표시명은 ScreenTo3D이며 승인된 그림은 유지한다. |
| 임시 파일·스레드·실험 모듈명 | `desktop.py`, `media_process.py`, `model_downloads.py`, `ovda.py`, `rowflow.py` | 사용자 설정과 무관한 내부 이름이다. 추후 묶어서 변경 가능하다. |
| 노출 가능한 옛 안내 | `gpu_preview.py:14`, 레거시 `gui.py`, 문서 제목 | 이전 미리보기/GUI 경로의 안내와 제품·구조·벤치마크 문서 제목에 남아 있다. 다음 이름 정리의 우선 후보다. |
| 과거 기록·이관 상수 | `docs/evidence/`, `docs/releases/`, `user_data.py:10` | 재현 가능한 당시 이름과 기존 경로 인식에 필요하다. 원문 보존이 적절하다. |

세부 파일·행·분류와 환경변수 목록은 로컬
`out/data-root-20261113/name-audit.json`에 보관했다. 요청의 두 번째 항목은 조사로
처리했으며, 저장 경로 외 모듈·프로토콜·설정 이름을 일괄 변경하지 않았다.

## 검증 및 실행본

- CPU/Qt 계약 540개 통과. 이관 전용 10개는 신규 설치, 멱등 이관, 새 로그가 있는
  루트로 병합, 충돌 보존, 권한 실패, 링크 거부, 공통 경로, Store 분리,
  Windows DPAPI 영수증 재사용을 포함한다.
- 실제 VDA 캐시를 사용하는 GUI 파일 변환: 320×192와 320×180 각 12프레임.
  Half Top-and-Bottom 출력 크기·프레임 수·오디오 및 전체 디코드 통과.
  이전에 검증한 로컬 FFmpeg를 사용했고 추가 미디어 설치는 하지 않았다.
- 저장소 루트 EXE를 백업한 뒤 새 네이티브 실행기로 갱신했다. 개발용 실행과
  최종 ZIP 추출본 모두 Windows 기본 PATH에서 앱 창이 뜨고 정상 종료했다.
- 최종 로컬 실행본: `out/data-root-20261113/final/ScreenTo3D-1.0.0/ScreenTo3D.exe`.
  ZIP: `out/data-root-20261113/final/assets/ScreenTo3D-1.0.0-windows-x64.zip`.
  SHA-256: `e57ad004d14b23c73a4f00a89e657fabf4cc81a5d8a369d7e54756e8b3f56e95`.
  이 실행본은 앞선 로컬 VDA 참조 검증 수정도 포함한다.

파일 이동과 실행·변환 검증은 입체 화질의 새 시각 평가를 뜻하지 않는다.
