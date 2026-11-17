# Pretendard UI 적용 결과

- 날짜: 2026-11-15
- 승인: 한글은 Pretendard 승인 후, 영문·숫자도 같은 글꼴로 통일하는 권장안 진행.
- 적용 범위: 정상 Qt/QML 데스크톱. 레거시 Tk 진단 GUI와 Windows가 그리는 네이티브 제목표시줄은 별도다. 기존 공개 ZIP/릴리스는 교체하지 않았다.

## 변경

- 공식 v1.3.9의 원본 PretendardVariable.ttf(6,739,336바이트)를 포함했다. Git blob 32b0811eae2cbfeb5f6ddaf34015ecaa726b006a로 공식 트리의 파일과 동일함을 확인했다. SHA-256/크기/공식 URL을 font-manifest.json에 기록하고 원본 OFL/copyright notice를 함께 넣었다.
- typography.py는 QML/오류창 생성 전에 프로세스 내부에 한 번만 글꼴을 등록한다. OS 설치나 실행 중 네트워크 요청을 하지 않는다. QApplication 기본 family와 14px/400을 설정하고 Theme는 Application.font.family를 읽어 모든 QML Text/Control과 일치시킨다.
- Segoe UI를 직접 지정하던 오류창과 VFG 안내를 공통 family에 연결했다. 일반 액션/선택 값은 500, 주요 액션/제목은 600, 일반 본문은 400이다. 소스 보조 문구는 11→12px로 조정했다.
- 사용자 지정 성능 정보 8px/green/6px 여백, VFG 14px 및 Half 형식의 축 보정은 유지했다.
- 포터블 builder가 글꼴·라이선스 해시를 확인하고 원본 앱 자산을 포함한다. 상위 licenses/Pretendard-OFL-1.1.txt와 THIRD_PARTY_NOTICES에도 반영했다. 글꼴 손상 시 앱 접근을 막지 않고 시스템 family와 진단 로그를 사용한다. 배포 전 검증에서는 손상을 실패로 처리한다.

## 자동 검증

- 전체 CPU 회귀: 640개, 639 통과/기존 symlink 권한 1 skip (`out/font-cpu-final.log`). 새 typography 테스트 3개는 포터블 한글 경로 복사·실제 파일 로딩 1회, 한글/영문/숫자의 단일 glyph family와 400/500/600 실제 굵기, 오류창/본문 14px, 자산·라이선스 손상 검출, 실패 시 앱 접근을 검증한다.
- 전체 이중언어 UI: `out/font-implementation-20261115/desktop-{100,150,200}/report.json` 전부 passed. 실제 DPR 약 1.0/1.5/2.0, 각 26개 캡처. 창/모니터 선택, 설정, 파일 변환과 긴 영어·라이선스 문구, 도움말, 키보드 조작, 오류 복사·언어 변경, 네 가지 형식의 VFG 안내 및 기존 타이머를 확인했다. OS 종료 명령은 금지 mock으로 차단했다.
- 새 조작·단축키 안내: `out/font-implementation-20261115/shortcut-ui/report.json` passed. 최소 폭·영한·키보드/바깥 클릭·충돌 대체 버튼 유지.
- 별도 오버레이: `out/font-implementation-20261115/overlays`, `overlays-100`, `overlays-200` 모두 passed. 실제 앱 소유 창에 합성 호스트 이미지를 표시하고 성능 정보를 강제 노출한 시각/속성 검사다. 네 입체 형식에서 양안 각각 Pretendard, 성능 8px/green, VFG 14px를 확인했다. 모델 추론/게임 FPS/실제 Owl3D 수용 검증으로 해석하지 않는다.
- QML 변경 9개 파일/15줄: qmllint와 전용 linter 0건. A1–A7 inline 검토, 추가 고확신 결함 없음. 타입 디자인 detector [] 반환. 번역 2언어/167 오류 ID/883개 유효. git diff --check 통과.

## 시각 확인

- 한국어/영어 메인·설정·오류창과 100%/200% 캡처 및 작은 오버레이를 직접 확인했다. 혼합 글자 family의 균일성과 600 제목/400 본문 대비가 이전 Segoe UI/Gulim 조합보다 안정적이다.
- 앱을 완전히 종료하고 다시 실행해야 기존 프로세스에도 적용된다. 실제 Owl3D에서의 8px 가독성은 사용자 기기 수용 확인으로 남긴다. 글꼴 변경을 추론/출력 FPS 개선으로 주장하지 않는다.
