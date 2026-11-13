# VFG isolated experiment

This directory prepares the 2x NVIDIA Maxine Video Frame Generation comparison.
It includes a standalone probe and an explicit Small/Base native-output prototype.
It is not a normal GUI backend. Current execution status is owned by
[implementation-status](../../docs/implementation-status.md#vfg-experiment).

The [2026-11-05 execution record](../../docs/evidence/vfg-experiment-20261105.md)
contains standalone results and limitations; the
[native execution record](../../docs/evidence/vfg-native-20261106.md) covers the
later application experiment. Normal application defaults remain unchanged.

## Access and provenance

Obtain the Windows x64 **VFX SDK Core** and **nvVFXVideoFrameGeneration** feature
from NVIDIA NGC. The core alone contains no feature model. The official sample
at revision `52011f89c1741d06b40ea312af1f20be8be9ec62` requires feature 1.3.0.0.
For RTX 5090, the documented feature installer accepts `-gpu 120`.
Use the matching installed core/feature versions and inspect their manifests.
The catalog's `*_woa` package is Windows ARM, not this machine's target.

Follow [NVIDIA's installation instructions](https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/InstalltheVFXSDK.html).
Keep the NGC key in local configuration; never put it in a command log, report,
repository or chat. Record downloaded archive origin/version/SHA-256 and actual
model terms before loading. The official sample source is MIT; the SDK and models
have separate terms. Download access is not distribution clearance.

The tested CLI email-login session can download the feature directly:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
ngc registry model download-version nvidia/maxine/nvvfxvideoframegeneration:1.3.0.0_lib_windows --dest out/vfg-access-20261105 --format_type json
```

This avoids a CP949 progress-display error on this Windows environment. The
SDK's `install_feature.ps1` reads an API key, not the CLI email-login session.
The downloaded VFG library package was sufficient to load/run the effect here;
the queried feature version list had no separate SM120 model package. Extract
the feature ZIP into `VideoFX/features` as the official installer does.

## Build and execute

In a Visual Studio x64 developer shell with CMake and CUDA Toolkit available:

```powershell
cmake -S experiments/vfg -B out/vfg-probe-build -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release "-DVFXSDK_ROOT=$((Resolve-Path out/vfg-sdk-1.3.0.0/VideoFX).Path)"
cmake --build out/vfg-probe-build
$env:PYTHONPATH='v1;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/run_probe.py --output out/vfg-new-run
```

The runner checks the three tested SDK DLL hashes, hashes its executable and
verifies input PNG hashes before execution. Use only the official SDK archive
and its dependencies. It runs one GPU process at a time with a 180-second bound,
records stage/exit failures and returns nonzero if any configuration fails.
Generated RGBA intermediates are replaced by lossless PNGs; summaries/logs remain.

`prepare_public.py --output <new-folder>` creates native Base FP16 SBS references
from the existing hash-verified public corpus. Run `run_probe.py --fixtures
<new-folder>/OfficeWalk --sizes 7680x2160 --output <new-result-folder>` (similarly
for the other clips). `--automatic-cut` compares the SDK's cut policy separately.
Public inputs retain source attribution and transformation/provenance records.
Their natural motion is called `translation` only to reuse the probe's case slot;
it is not constrained planar motion. Fixed-disparity metrics apply only to the
synthetic inputs. `3840x2160` is available for explicit per-eye fixtures marked
`layout: mono`, without misleading SBS seam metrics on a single eye.

## Deterministic inputs

Using the prepared local Python environment from the repository root:

```powershell
$env:PYTHONPATH='v1;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/prepare_fixtures.py --output out/vfg-fixtures-new
```

The output directory must not already exist. The generator creates 9 cases at
640x180, 3840x1080 and 7680x2160 Full SBS. Each has previous, current and expected
images, with hashes in `manifest.json`. Cases are identity, an exact translated
textured plane, and a manual cut whose expected result is the current frame.
Translation uses 8 px endpoint motion, a 4 px true midpoint and 12 px stereo
disparity; offsets are deliberately fixed across resolutions. PNGs are lossless
8-bit RGB (OpenCV reads BGR). Convert explicitly to BGRA8/RGBA8 for the effect.
The official sample's still-image mode instead uses RGB10A2 and 16-bit input;
do not pass these PNGs through that mode as an 8-bit GPU-path measurement.

These inputs contain no capture or model output. They test controlled geometry;
they cannot establish natural-video occlusion or perceptual binocular quality.

## Measurement contract

1. Build against actual official headers/libraries, in an isolated output folder.
   Start with a small image, then attempt both large Full SBS shapes; record load
   or run errors as unsupported in that tested configuration, without resizing.
2. Use one owned CUDA stream, matching GPU RGBA8 inputs/output, mode set before
   load, multiplier 2 then frame index 1. Rebind **both** input images for every
   new pair, even when addresses stay the same. Reset manual shot-change to 0
   after a cut. Run identity/translation/cut followed by translation again.
3. Synchronize/read the generated image before reuse of the single SDK output;
   retain inputs until completion. Fail visibly on allocation/load/run errors.
   Stop submission and drain before releasing buffers, effect and stream.
4. Time warmup/load separately. For each accepted shape and Low/Medium/High,
   discard warmup and report five bounded repeats, CUDA execution and host
   submission/synchronization separately. Exclude PNG I/O from GPU timing.
5. Report full-image error against the true midpoint, separate eye errors,
   disparity-aligned residual on overlapping pixels and the center seam band.
   Manual cut must copy current, and the following pair must interpolate again.
   Compare automatic cuts separately. Per-eye runs, if tested, use identical
   timestamps and a shared cut decision; they are a different comparison path.
6. Follow with held-out real SBS midframes from the current depth/stereo path.
   Measure actual native original/generated presentation counts, pair age,
   drops/queue bounds and stop/restart ownership under model contention. Pure
   VFG GPU timing or a 2x arithmetic multiplier is not native application FPS.
   Waiting for the next source frame adds lookahead; measure it explicitly.

The standalone probe and native launcher cover the bounded measurement portion
of item 6. Continuous perceptual review and long-session acceptance remain separate.

## Native prototype

Use the prepared local app dependencies and trusted Base FP16 artifacts. Build
the bridge with the installed Visual Studio 2022 and CUDA 13.1 toolchain:

```powershell
& experiments/vfg/build-native.ps1
$env:PYTHONPATH='v1;experiments/vfg;scripts;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/check_native_bridge.py --output out/vfg-parity-new
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/benchmark_native.py --output out/vfg-baseline-new
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/benchmark_native.py --vfg --lifecycle --output out/vfg-native-new
& out/vda-oracle-env/Scripts/python.exe experiments/vfg/benchmark_native.py --vfg --size 1920x1080 --warmup 2 --seconds 3 --repeats 2 --test-cut-every 30 --lifecycle --output out/vfg-cut-new
```

Run GPU commands sequentially and choose new output directories. The launcher
opens its own public test source and native SBS window; keep the source visible
on the active desktop throughout the run. Minimization or desktop changes can
correctly trigger source-loss safety shutdown. It closes its own windows on exit.
The bridge and SDK DLL pins are verified before loading; a rebuilt binary with a
different hash requires validation and an explicit pin update, not a bypass.

The default measurement uses 4K input, 4 seconds warmup and five 4-second windows.
`--vfg` is required for Medium interpolation; reports record this flag and reject
a requested VFG run without observed generated output. Baseline and VFG use the
same timing observer. Counts come from distinct Qt `afterFrameEnd` output IDs;
original FPS, generated FPS and fresh inference FPS are separate. Age measures
capture/source timestamp to Qt completion, not physical input-to-photon latency.
Generated midpoint age and oldest-input age are both recorded. Full SBS textures
are fitted into a 1400x650 output window. Private process bytes are not VRAM.

Three owned linear GPU frames plus the existing two shared native slots bound
frame storage. Real slot ownership is acquired just before GPU publication;
per-frame GUI notification permits both members of the pair to render. Test-only
forced cuts validate reset handling, not the app's ability to detect natural cuts.
The launcher patches renderer/delivery only inside its experiment processes;
neither GUI settings nor the shipped backend list gains a VFG option.

## 실사용 A/B 비교

준비된 이 체크아웃에서 다음 실행 파일을 더블클릭합니다.

- **A · 기존 SBS:** 저장소 루트의 `Run-Compare-A.cmd`
- **B · VFG 적용:** 저장소 루트의 `Run-Compare-B-VFG.cmd`
- **Small · VFG 없음:** 저장소 루트의 `Run-Compare-Small.cmd`
- **Small · VFG 적용:** 저장소 루트의 `Run-Compare-Small-VFG.cmd`

1. 일반 ScreenTo3D와 다른 비교 앱을 닫습니다. 게임은 창 모드 또는 테두리 없는
   창 모드로 준비하거나, 비교할 영상을 재생합니다.
2. A를 열고 입력 창을 선택한 뒤 **SBS 시작**을 누릅니다. 원하는 화면으로
   SBS 창을 옮기고 F11로 전체 화면을 켭니다. Esc로 돌아옵니다.
3. 같은 장면에서 카메라 회전, 움직이는 물체 가장자리, 가려졌다 나타나는 부분,
   자막/HUD와 조작 반응을 확인합니다. 초기 준비가 끝난 뒤 비교합니다.
4. **SBS 중지 → A 앱 닫기 → B 실행** 순서로 전환합니다. 같은 입력 창을
   다시 선택하고 같은 해상도·입체 강도·FPS 제한으로 동일한 장면을 확인합니다.
   두 앱에서 SBS를 동시에 실행하면 GPU 경쟁으로 비교가 달라집니다.

A/B는 균형(DA2 Base FP16), Small 실행기는 빠른 처리(DA2 Small FP16)로
시작합니다. 모두 GPU 직접 출력, **60 FPS**, **입체감 0.5**가 기본이며
입체감의 ‘기본값’ 버튼도 0.5로 돌아갑니다. Small을 비교할 때도 기존 앱을
중지하고 닫은 뒤 같은 입력 창과 조건으로 실행하세요. Small VFG 실행기도
Base와 같은 Medium 2x 보간을 사용합니다. 이 시험은 창 캡처 전용이며 실행기 지정 모델 외의 모델,
모니터 전체 캡처·호스트 출력을 지원하지 않습니다. 설정을 바꿔 지원 범위를
벗어나면 시작 전에 별도 오류창으로 알립니다.
일반 `Run-ScreenTo3D.cmd`는 VFG가 기본으로 꺼져 있으며, **화질과 입체감 → 프레임 보간 (VFG)**에서 켤 수 있습니다.
이 문서의 A/B 비교 실행기는 정해진 비교 방식을 유지하므로 해당 스위치를 표시하지 않습니다.

네 비교 실행기는 최신 깊이 범위 시간 안정화를 자동으로 사용합니다. 입체감
0.5와 기존 윤곽 보정을 유지하며, 정지 영역으로 확인되는 모델의 깊이 배율·이동을
보정한 뒤 깊이 범위의 작은 흔들림을 완화합니다. 변경 전에 열었던 앱은 완전히
닫고 다시 실행하세요. 실제 눈의 편안함과 움직이는 물체의 품질은 직접 비교가
필요합니다.

Owl3D의 3D 기능을 켰을 때도 결과를 읽을 수 있도록 **네 비교 실행기의 SBS
출력 창은 외부 캡처를 허용**합니다. 이는 Owl3D만 허용하는 방식은 아니므로
다른 화면 캡처 앱에도 SBS 결과가 보입니다. 제어창·설정창·오류창의 보호는
유지합니다. 일반 `Run-ScreenTo3D.cmd`는 기존 캡처 차단을 유지합니다.
수정 전에 열었던 비교 앱은 완전히 닫고 다시 실행해야 적용됩니다.
입력과 출력은 같은 모니터에 있어도 되지만, 입력에는 원본 게임·영상 창을
선택해야 합니다. ScreenTo3D 출력 창 자체는 목록에서 제외하고 시작 시에도
거부하므로 다른 비교 앱의 출력으로 재캡처할 수 없습니다.

Owl3D에서는 **Stereo 3D Playback / SBS Mode / Native 3D**에 해당하는
재생 기능을 사용합니다(표시는 버전에 따라 다를 수 있습니다). ScreenTo3D의
출력 형식은 **Full-SBS**입니다. SBS 창을 Shift로 옮기고 **F11 전체 화면**으로
확인합니다. 입력 게임 자체는 ScreenTo3D가 선택한 원본 창을 그대로 유지합니다.

**SBS 모드와 Full SBS를 지정했는데도 두 화면이 그대로 보였던 문제:**
비교 출력 창의 Windows 소유 관계를 수정했습니다. 이전에는 작은 제어창에
딸린 보조 창이었지만 이제 독립된 최상위 창입니다. 수정된 창으로 Owl3D의
전체 화면 인식, FullSBS 판정과 `weave enabled` 로그까지 확인했습니다.
예전 비교 앱은 반드시 완전히 닫고 다시 실행해야 합니다. 형식 설정만 바꿔서
해결되는 문제로 단정하지 마세요. 시험에서는 Auto에서도 FullSBS를 인식했지만
실제 눈으로 보는 입체 품질은 별도 확인이 필요합니다.
Shift는 공식적으로 Full/Half-SBS와 Native 3D 재생을 지원합니다.
[Shift 안내](https://www.owl3d.com/shift),
[Owl3D 공식 답변 — Stereo 3D Playback](https://www.owl3d.com/shift/reviews).

창 제목에 **모델/A·B 종류 · 출력/원본/보간 FPS · 지연**을 약 2초마다 표시합니다.
작은 제어창에서 제목이 잘리면 SBS 출력 창의 제목을 확인하세요. ‘원본’은 새
SBS 프레임, ‘보간’은 VFG가 만든 중간 프레임입니다. 지연은 캡처 시각부터
Qt 프레임 완료까지의 최근 중앙값으로, 실제 모니터의 표시 지연과 다릅니다.
전체 화면에서는 제목이 숨겨지므로 Esc로 확인할 수 있습니다.

입력 창을 최소화하거나 가상 데스크톱을 바꾸면 캡처 안전 검사로 중단될 수
있습니다. SBS 창 자체의 숨김/복원은 지원합니다. 시험에 시간 제한은 없지만
장시간 안정성이나 실제 게임의 입체 화질은 아직 검수되지 않았습니다.

결과는 `out/vfg-comparison/<시각>-A-baseline/`, `…-B-vfg/`, `…-A-small/`, `…-B-small-vfg/` 아래의
`session-1.json`, `session-2.json` 등에 저장됩니다. 시작/중지마다 세션을
구분하고, 최근 최대 60개 측정 구간과 종료 시 자원 정리 상태를 남깁니다.
화면 이미지·영상·선택한 창 제목은 저장하지 않습니다. 실행기 표준 오류 로그는
각 결과 폴더 옆의 `.stderr.log`이며, 앱이 열리지 않을 때 확인할 수 있습니다.
비교 앱의 출력 위치는 별도로 기억하므로 일반 앱 설정을 덮어쓰지 않습니다.

API details: [NVIDIA VFG](https://docs.nvidia.com/maxine/vfx/latest/Filters/VideoFrameGeneration.html).
Source: [official sample at the pinned revision](https://github.com/NVIDIA-Maxine/VFX-SDK-Samples/tree/52011f89c1741d06b40ea312af1f20be8be9ec62/apps/VideoFrameGenerationEffectApp).
