# 문서·앱 패키지·Git 이력 경로 정리 — 2026-11-13

사용자는 커밋 이메일 공개를 허용하고 유지를 요청했으며, 문서와 앱 ZIP의 개인 경로
정리 및 Git 이력 재작성을 승인했다. 원격 push·릴리즈 교체는 이번 작업에 포함하지 않았다.

## 수정

- 문서의 사용자 홈 경로 2곳은 `%USERPROFILE%` 예제로 치환했다.
- 모델 측정 문서 3개에 반복된 개인 영상 경로 17곳은 `samples/input.mp4`로 바꿨다.
- `portable_package.exclusion()`에서 라이선스 폴더 보존 규칙보다 bytecode 제외를
  먼저 적용한다. `__pycache__`, `.pyc`, `.pyo`는 라이선스 폴더 안에서도 제외한다.
  실제 라이선스 텍스트와 `packaging.licenses`의 Python 소스는 유지한다.
- 빌더의 일반 디렉터리 복사에도 같은 bytecode 확장자 제외를 적용했다.
- 현재 소스로 새 앱 폴더와 ZIP을 빌드했다. 기존 배포·검증 자산은 덮어쓰지 않았다.

## Git 이력

109개 커밋의 부모 관계와 전체 트리를 대응시켜 승인된 문자열 치환만 적용됐는지
확인했다. 커밋 작성자·커미터 이메일, 날짜, 메시지는 모두 보존했다. 릴리즈 태그의
대상 커밋은 새 이력으로 바뀌고 태그 작성자와 메시지는 유지된다.
로컬 작업 스냅샷 tree 참조의 경로도 정리했다.

- 이전 HEAD: `b3b76868eb9348c9a74228591a8521acf417eaaa`
- 새 HEAD: `bcbae96f6900e6a01a786ba729ee73006d4cf03d`
- 이력 적용 직전 미커밋 파일 878개의 내용 해시와 비어 있던 staging 상태를
  이력 적용 후 대조해 보존을 확인했다.
- 복구용 전체 Git bundle과 작업 파일 ZIP은 Git에서 제외된
  `out/privacy-fix-20261113/`에 보존한다. 원본 reflog·도달 불가능한 객체의 삭제는
  수행하지 않았다. 이 로컬 복구 데이터에는 정리 전 경로가 남을 수 있다.
- 원격 저장소와 기존 GitHub 릴리즈 파일은 변경하지 않았다. 원격 반영 시에는
  보관한 이전 ref를 기준으로 lease를 확인하는 강제 갱신이 필요하다.

## 검증

- 수정 전: 라이선스 폴더 내 캐시 제외 회귀 테스트의 5개 subcase가 실패했다.
- 수정 후: 필터 10개와 릴리즈 패키징 6개 테스트가 모두 통과했다. 실제 ZIP 생성
  테스트는 캐시가 빠지고 `COPYING.LIB`가 보존되는지 확인한다.
- 새 앱 ZIP: 3,246항목, **182,755,816 bytes**, bytecode 항목 0개.
  SHA-256: `2629fc86fad4866add859919f31665a867cd8b34243e7c57ef7f4595960ed8bd`.
- 기존 앱 후보 ZIP의 실제 라이선스 파일 48개를 새 ZIP과 byte 단위로 대조해
  같음을 확인했다. 앱 소스 파일 139개의 빌드 매니페스트 해시도 일치했다.
- 당시 현재 파일 878개와 도달 가능한 Git blob 1,488개, 새 앱 ZIP의 모든 구성원에서
  알려진 개인 경로의 ASCII·UTF-16LE 문자열이 검출되지 않았다.
- 새 ZIP을 새 폴더에 풀어 EXE를 실행했다. Windows 기본 PATH만으로 소유된
  메인 창이 나타나고 닫기 후 exit 0으로 종료했다.
- 패키저의 공식 런타임 4종 및 공개 모델 2종 익명 URL·크기·ZIP prefix 점검이
  모두 통과했다. 전체 원격 파일을 재다운로드해 해시를 검증한 결과는 아니다.

새 자산은 `out/privacy-fix-20261113/assets/`에 있으며, 경로가 정리된 현재 소스
snapshot도 `ScreenTo3D-1.0.0-source-refresh.zip`으로 함께 준비한다.
체크섬 파일은 해당 폴더의 실제 자산을 기준으로 생성한다.

근거: 같은 출력 루트의 `red.log`, `final-filter.log`, `final-packager.log`,
`history-prepared.json`, `history-applied.json`, `tree-residual-cleanup.json`,
`artifact-verification.json`, `launcher.json`, `source-verification.json`.
검사는 알려진 경로의 회귀 확인이며 전용 비밀 탐지 엔진이나 전면 개인정보 검증을
대체하지 않는다. GPU 추론·입체 화질은 이번 변경 대상이 아니므로 재평가하지 않았다.
