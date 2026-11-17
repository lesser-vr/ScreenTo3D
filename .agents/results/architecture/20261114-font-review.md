# UI 글꼴 변경 검토

- 날짜: 2026-11-14
- 후속: 승인 후 2026-11-15에 구현했다. [적용·검증 결과](20261115-font-implementation.md)를 참조한다. 아래는 당시 비교 검토 기록이다.
- 결론: 기존의 절제된 밝은 유틸리티 디자인에는 **Pretendard Variable**을 우선 권장한다. SUIT는 대안, Noto Sans KR는 비교 기준이다.
- 범위: 임시 QML 복사본과 프로세스 내 글꼴 등록만 사용했다. 앱 소스, OS 설치 글꼴, 설정, 실행 중인 사용자 앱은 변경하지 않았다. 실제 앱에 적용한 상태가 아니다.

## 현재 상태와 근거

- Theme.qml의 기본 family는 Segoe UI다. Main.qml은 14px, 설명 11–13px, 제목 17/22px, 보통/Medium/DemiBold/Bold를 사용한다. 오류창은 error_dialog.py에서 Segoe UI 10pt를, VFG 안내는 VfgNotice.qml에서 Segoe UI 14px를 직접 지정한다. 레거시 Tk gui.py에도 별도 지정이 있다.
- 실제 소스 선택기의 QFont로 ‘실시간 3D · 전체화면 전환 · Ctrl+Alt+Enter’를 QTextLayout에 통과시킨 결과, 현재 경로의 글리프 run은 Segoe UI와 Gulim으로 나뉘었다. Qt/Windows의 이 PC·이 문장에 대한 결과이며 모든 PC/문자의 fallback을 단정하지 않는다.
- 한글/영문/숫자 혼합 텍스트에서 굵기와 인상이 달라진다. 기존 500/600/700 지정도 한글 fallback에서 같은 수준으로 구분된다고 볼 수 없다.

## 같은 조건의 실제 Qt 비교

`out/font-review-20261114/main-comparison.png`, `guide-comparison.png`.

| 후보 | 시각 평가 | 샘플 혼합 문장 폭(14px) |
|---|---|---:|
| 기존 Segoe UI + Gulim fallback | 한글이 상대적으로 가늘고 오래된 인상, 한영 굵기 차이 | 262.20 |
| A Pretendard Variable | 한영/숫자 일관성이 좋고 단정함. 현재 디자인에 가장 적합 | 244.67 |
| B SUIT | 깔끔하고 중립적. 보수적인 본문/컨트롤 대안 | 254.28 |
| C Noto Sans KR | 가독성은 좋지만 이번 화면에서 제목이 더 묵직한 인상 | 259.14 |

- 측정은 앱과 같은 Qt 글꼴 엔진, DPR 1.5 및 420x260에서 수행했다. Pretendard/SUIT/Noto의 샘플 run은 각자의 단일 family로 해결됐다. 폭은 이 문장 하나에 대한 값이며 모든 문장의 폭/레이아웃을 보증하지 않는다.
- 비교는 동일한 색, 크기, 굵기를 유지했다. 한국어 메인/조작 안내 및 영어 안내를 렌더링했다. 파일 변환·설치·오류 전체 및 100%/200% DPI 검증은 아직 하지 않았다. 실제 3D나 게임 FPS 측정은 아니다.

## 동봉 용량과 배포

- 비교용 설치 파일: Pretendard Variable Version 1.309, TTF 6.43 MiB, DEFLATE 수준 6으로 글꼴만 압축 시 2.82 MiB.
- SUIT Version 2.040의 Regular/Medium/SemiBold/Bold 정적 TTF 4개 합계 2.26 MiB, 같은 압축 조건 1.00 MiB.
- 이 수치는 현재 설치 파일의 실측이다. 최종 배포에 고정하는 공식 버전/파일 형식에 따라 달라진다. 설치 파일을 그대로 배포 확정한 것은 아니다.
- Pretendard와 SUIT 모두 공식 저장소에서 OFL-1.1 사용/재배포 조건을 확인했다. 적용 시 공식 원본과 저작권/라이선스 고지를 함께 동봉한다. 시스템 설치나 CDN 접근 없이 앱의 QFontDatabase.addApplicationFont로 읽는 방식을 권장한다.

## 적용 권장 범위

- 본문 400, 일반 컨트롤/선택 값 500, 주요 버튼/제목 600을 중심으로 조정한다. 현재 700 제목은 Pretendard에서 더 강하게 보이므로 600을 먼저 비교한다.
- 본문 기본 14px를 유지하고 기존 11px 보조 문구는 12px 가독성을 별도 비교한다. 파일명/모델명/키 배지/팝업의 380px 최소 폭과 영어 긴 문구를 확인한다.
- 공통 앱 글꼴 로더와 Theme를 통일하고, 직접 지정된 오류창/VFG 안내에도 같은 기준을 적용한다. 한 군데 family만 바꾸면 모든 Text/오류창에 전파된다고 가정하지 않는다.
- 사용자가 지정한 8px 성능 오버레이와 14px VFG 안내 크기는 유지한다. 특히 8px 숫자/영문은 작은 크기의 선명도를 별도 비교하고 결정한다. Windows가 그리는 네이티브 제목표시줄은 별도 영역이다.
- 언어별로 다른 family를 섞거나 사용자에게 새 글꼴 선택 옵션을 노출할 필요는 없다.

## 공식 자료

- Pretendard 소개: https://github.com/orioncactus/pretendard
- Pretendard 라이선스: https://github.com/orioncactus/pretendard/blob/main/LICENSE
- SUIT 소개: https://github.com/sun-typeface/SUIT
- SUIT 라이선스: https://github.com/sun-typeface/SUIT/blob/main/LICENSE

추천은 현재 앱의 실제 Qt 렌더링에 대한 디자인 판단이다. 저자의 가독성 소개를 객관적인 앱 사용성 시험으로 취급하지 않았다. 최종 선택과 실제 기기 가독성은 사용자 확인이 필요하다.
