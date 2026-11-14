# 3D 출력과 원본 입력 포커스 분리 구현·검증

- 날짜: 2026-11-14
- 범위: 승인된 1차 포커스 개선. 커밋·push·릴리스 교체는 수행하지 않음.
- 기존 표시 주기, 브랜드 실행 호스트, 오류 기록 변경은 보존함.

## 구현

- 출력 Window는 생성 때부터 WindowDoesNotAcceptFocus를 선언하고, 네이티브 WS_EX_NOACTIVATE를 유지한다. 일반 클라이언트 클릭은 MA_NOACTIVATE로 처리하며 마우스 메시지를 삼키거나 다른 모니터로 주입하지 않는다.
- 제목표시줄/테두리, 크기 조절 모달 루프와 우클릭/시스템 메뉴만 관리 상태로 전환한다. 종료 후 직전의 유효한 외부 입력 창 또는 HWND/PID가 검증된 원본으로 1회 복귀한다. 사용자가 다른 앱으로 전환했다면 복귀하지 않는다.
- 첫 프레임 뒤에는 앱 제어창/출력이 여전히 foreground일 때만 원본 활성화를 1회 시도한다. 모니터 캡처는 임의의 창을 고르지 않는다. 최소화·숨김·DWM cloak·재사용된 핸들은 제외하며 Windows 활성화 제한을 우회하지 않는다.
- Ctrl+Alt+Enter는 출력이 실행·표시되는 동안만 전역 등록한다. 단축키 충돌은 기존 번역 메시지로 도움말에 표시하고 실시간 출력 설정의 전환 버튼을 남긴다. F11/Esc는 로컬 키로 유지한다. VFG Ctrl+Alt+S는 변경하지 않았다.
- 기본 페이지의 새 조작 버튼은 없다. 출력 설정에 전환 버튼과 도움말을 제공한다. 사용 안내는 영어·한국어에 반영했다.
- 일반 출력은 비활성 TopMost로 유지한다. Owl3D display-mirror.exe의 겹치는 최종 출력과 활성 앱 제어창/오류창 중 더 아래에 있는 창의 뒤로 배치한다. 외부 창은 수정하지 않는다. 앱의 작업표시줄 항목은 유지하고 비활성 출력은 별도 항목을 요구하지 않는다.
- Windows foreground/창 show-hide-destroy 이벤트를 구독하고 관리/이동/크기/전체화면 전환 시 처리한다. 프레임별 포커스·창 열거 폴링은 없다. VFG 재시작 중 원본 대상과 단축키 등록을 유지하고, 종료 때 구독·단축키·대기 복귀를 정리한다.

## RED와 수정

- 정책 테스트를 먼저 추가하여 미구현 모듈의 ImportError를 확인한 뒤 구현했다.
- 실제 창 테스트에서 Qt의 초기 활성화 요청을 관리 상태로 오인하여 NOACTIVATE가 해제되는 회귀를 발견했다. 최초 QML 플래그와 실제 foreground 확인을 추가했다.
- NOTOPMOST만 지정하면 일반 오류창보다 위로 올라갈 수 있어, 활성 제어창/최종 Owl 렌더러의 뒤로 실제 배치하도록 보완했다.

## 최종 검증

- `python -m unittest discover -s v1/tests`: 628개, 성공 627개, 기존 심볼릭 링크 권한 테스트 1개 skip. `out/output-focus-cpu-final.log`.
- 새 포커스/브리지/표시 순서 회귀: 21개 통과. 늦은 준비 완료, 메뉴 중 준비 완료, HWND/PID 재사용·비가시 상태, 모니터 캡처, 외부 입력 대상 보존, Owl renderer 제외, 메뉴/이동 복귀, Qt 초기 활성화, 전역 키 충돌·해제, VFG 재시작, 프레임 폴링 부재 등.
- 실제 Small GPU 캡처/추론/Qt D3D11 출력: `out/output-focus-20261114/native-final-2/report.json` passed. NoActivate/TopMost, 클라이언트 클릭 메시지 유지, 전체화면 3회 왕복과 HWND 유지, 네이티브 크기 루프, 실제 QML 메뉴 열기/닫기, Windows 이벤트 훅 2개 등록, WM_HOTKEY 디스패치, 중지 후 live_pools/live_nodes=0을 확인했다.
- 실제 창 테스트는 `--background` 모드다. 무인 실행의 첫 foreground 활성화가 Windows에 거절되어 강제 활성화 우회는 하지 않았다. 원래 foreground가 바뀌지 않는지 검증했고, 실제 사용자 클릭 이후의 원본 포커스 복귀는 정책/메시지 회귀 통과와 구분한다.
- 제어창 렌더링 회귀: `out/output-focus-20261114/window-updates/report.json` passed. 미리보기 off에서 75 notifications / control 0 / output 74, on에서 75 / 74 / 74, 다시 off에서 75 / 0 / 74. 게임 FPS나 성능 향상 수치로 해석하지 않는다.
- 번역 검증: 2언어, 오류 ID 167개, 번역 863개 통과.
- QML review: diff Main.qml/LiveOptions.qml, 14개 추가·변경 줄. qmllint: ran (out/gui-python-deps/PySide6/qmllint.exe), deterministic lint 0 findings. Agents: 0 (inline). A1–A7에서 추가 고확신 결함 없음. git diff --check 통과.

## 남은 사용자/기기 수용 확인

- 앱을 완전히 종료하고 프로젝트의 ScreenTo3D.exe를 다시 실행해야 새 모듈을 로드한다. 실행 중인 사용자 앱은 종료하지 않았다.
- 원본 창에서 실제 키보드·클릭·드래그 중 3D 유지, 제목표시줄/테두리/우클릭 관리 후 원본 복귀, 다른 앱 사용 중 늦은 준비 완료를 확인한다.
- Owl3D 실제 장치의 최종 mirror/overlay 표시 순서, 커서/입체 화면의 조작감과 VFG 실사용 전환은 별도 수용 확인이 필요하다. 이번 테스트는 사용자 게임, Owl3D 설정이나 전역 마우스를 조작하지 않았다.
- 커서는 원본 모니터에서 조작한다. 다른 모니터의 3D 화면을 클릭해 원본에 좌표를 중계하는 기능은 이번 범위가 아니다.


## F11 후속 보완

- 사용자 확인: 미러링 창은 Owl 최종 renderer가 아니라 처음 선택한 Veyra 등의 원본 창이다.
- 재현: 기존 제목표시줄 클릭/이동 종료 메시지는 클릭만 한 경우도 즉시 복귀시켜 F11 입력이 원본으로 갈 수 있었다. 또한 전체화면 전환 자체에는 관리 종료 처리가 없었다. 새 회귀 2개가 각각 관리 상태 조기 종료/미종료로 실패(RED)했다.
- 수정: 제목표시줄 선택 이유를 별도로 보존하고 실제 geometry가 바뀐 이동·크기 조절에서만 종료한다. F11/Esc/전역키/설정의 공통 fullscreen 처리 뒤 취소 가능한 Qt 단발 타이머로 caption/click 관리 상태를 종료한다. 열린 메뉴는 자신의 종료 때까지 보존한다. 전환 중 다른 앱을 고르면 기존 foreground 검사로 포커스를 빼앗지 않는다.
- 범위: 기본 창/마우스 동작은 유지하며, 별도의 옵션이나 타임아웃 폴링은 추가하지 않았다. 단순 선택 뒤 F11을 기다리는 동안은 출력 관리 상태다. 실제 드래그를 마쳤으면 원본 복귀하므로, F11 사용에는 제목표시줄을 다시 클릭하거나 Ctrl+Alt+Enter를 쓴다.
- 정책/브리지 회귀는 23개 통과(GREEN). 전체 CPU 및 실제 GPU 회귀의 최신 결과는 `out/output-focus-f11-cpu.log`, `out/output-focus-f11-native.log`, `out/output-focus-20261114/native-f11-followup/report.json`을 참조한다. 무인 foreground 활성화 제한과 실제 사용자 F11/원본 복귀 수용 확인 범위는 위와 같다.
