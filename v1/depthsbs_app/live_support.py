"""Measured local operating guidance, not automatic resizing or support claims."""

LAB_CADENCE = {
    (1280, 720): "약 30 fps 출력 · 로컬 권장 시작점",
    (1920, 1080): "약 18 fps 출력 · 30 fps 미달",
    (3840, 2160): "약 3 fps 출력 · 실시간 비권장",
}


def guidance(width, height):
    result = LAB_CADENCE.get(
        (width, height), "이 해상도는 반복 성능 미검증 · 1280×720부터 권장"
    )
    return f"{result} (RTX 5090 / SDR 생성 창 실측). 자동 축소하지 않습니다."
