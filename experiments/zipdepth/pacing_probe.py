"""Opt-in bounded timestamp tracing for the owned-source timing benchmark."""
from collections import deque
import json
import os
from pathlib import Path
import time


def worker(*args, **kwargs):
    from depthsbs_app import presentation_policy
    from depthsbs_app.texture_mailbox import TextureMailbox
    from depthsbs_app.live_sbs import sbs_worker
    from trial import worker as zip_worker

    rows = deque(maxlen=16384)
    started = [0]
    original_cadence = presentation_policy.PresentationCadence
    original_work_cadence = presentation_policy.WorkCadence
    original_publish = TextureMailbox.publish

    class TracedCadence(original_cadence):
        def emitted(self, now):
            started[0] = now
            super().emitted(now)

    class TracedWorkCadence(original_work_cadence):
        def emitted(self, now):
            started[0] = now
            super().emitted(now)

    def publish(mailbox, frame):
        ready = time.perf_counter_ns()
        original_publish(mailbox, frame)
        rows.append((frame.sequence, frame.callback_ns, started[0], ready))

    presentation_policy.PresentationCadence = TracedCadence
    presentation_policy.WorkCadence = TracedWorkCadence
    TextureMailbox.publish = publish
    try:
        target = zip_worker if os.environ['DEPTHSBS_TIMING_MODEL'] == 'zipdepth' else sbs_worker
        return target(*args, **kwargs)
    finally:
        Path(os.environ['DEPTHSBS_TIMING_TRACE']).write_text(json.dumps(
            dict(columns=['sequence', 'callback_ns', 'started_ns', 'ready_ns'], rows=list(rows))), encoding='utf-8')
