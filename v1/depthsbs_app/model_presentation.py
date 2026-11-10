"""Model-oriented UI descriptions, without loading engines or importing CUDA."""
from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from .optional_models import available


def model_info(model, engine=''):
    if model == 'da2-small':
        return 'DA2 Small', 'FP16', (
            '처리 속도와 응답성을 우선하는 기본 모델입니다.\n\n'
            'FP16 모델 연산을 사용하며, 입출력과 일부 처리는 FP32입니다.')
    if model == 'da2-base':
        return 'DA2 Base', 'FP16 혼합', (
            'DA2 Small보다 큰 모델입니다. 처리 비용이 늘며, 장면에 따라 깊이 표현이 달라집니다.\n\n'
            'FP16과 FP32 혼합 정밀도입니다. 주요 모델 연산은 FP16, '
            '민감한 정규화·Softmax·Resize와 입출력은 FP32로 유지합니다.')
    if model == 'vda-small':
        from .vda_artifacts import uses_mixed_fp16
        installed = available(model, engine)
        mixed = not installed or uses_mixed_fp16(engine)
        precision = 'FP16 혼합' if mixed else 'FP32'
        detail = ('인코더의 주요 연산은 FP16, 시간축 처리·이력과 입출력은 FP32입니다.'
                  if mixed else '현재 선택된 엔진은 FP32입니다.')
        if not installed:
            detail += '\n미설치 상태에서는 설치될 모델 버전의 정밀도를 표시합니다.'
        return 'VDA Small', precision, (
            '이전 프레임을 활용해 깊이의 시간적 일관성을 높이는 방식입니다. '
            '실시간 출력에서는 현재 VFG를 지원하지 않습니다.\n\n' + detail)
    if model == 'ovda-small-c16':
        return 'oVDA c16', 'FP16 혼합', (
            '이전 프레임의 이력을 사용하는 별도 영상 깊이 모델입니다. '
            '소스 실행 전용이며 개인·비상업적 사용 조건을 확인해야 합니다.\n\n'
            '518×924 혼합 정밀도 엔진을 사용합니다. 인코더와 공간 attention은 FP16을 활용하며, '
            '시간축 처리·캐시·깊이 출력과 입출력은 FP32를 유지합니다.')
    raise ValueError('알 수 없는 깊이 모델입니다.')


def selection_info(mode, model, engines):
    name, precision, description = model_info(model, engines.get(model, ''))
    if mode == 'offline-quality':
        name += ' · 5프레임'
        description = ('파일 변환 전용입니다. VDA Small로 장면별 5프레임 문맥을 사용하며, '
                       '두 프레임을 미리 읽습니다.\n\n' + description.split('\n\n', 1)[1])
    label = f'{name} · {precision}'
    if mode == 'performance':
        label += ' · 기본'
    return dict(key=f'{mode}/{model}', mode=mode, model=model, label=label, help=description)


def selection_choices(modes, engines, *, portable):
    return [selection_info(mode, model, engines)
            for mode in modes for model in sorted(MODE_MODEL_CHOICES[mode], key=lambda m: m != DEFAULT_MODE_MODELS[mode])
            if not (portable and model == 'ovda-small-c16')]
