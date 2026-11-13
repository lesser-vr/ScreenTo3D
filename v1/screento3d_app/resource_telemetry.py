"""Constant-space counters and explicitly scoped device-memory observations."""
import time


class ResourceMetrics:
    def __init__(self):
        self.counters = {
            'h2d_submissions': 0, 'h2d_submitted_bytes': 0,
            'd2h_submissions': 0, 'd2h_submitted_bytes': 0,
            'stream_synchronizations': 0, 'completed_inferences': 0,
        }
        self.memory = {
            'scope': 'cuda_device_global', 'source': 'cudaMemGetInfo',
            'sample_interval_seconds': 1.0, 'sample_count': 0,
            'error_count': 0, 'last_probe_ok': None,
            'first_used_bytes': None, 'last_used_bytes': None,
            'sampled_max_used_bytes': None, 'last_total_bytes': None,
        }
        self.last_sample_time = None

    def copy_submitted(self, direction, size):
        if direction not in ('h2d', 'd2h') or size < 0:
            raise ValueError('invalid copy counter')
        self.counters[direction + '_submissions'] += 1
        self.counters[direction + '_submitted_bytes'] += size

    def sample_memory(self, query, *, force=False, now=None):
        now = time.perf_counter() if now is None else now
        if not force and self.last_sample_time is not None and now - self.last_sample_time < 1.0:
            return
        self.last_sample_time = now
        try:
            free, total = (int(value) for value in query())
            if not 0 <= free <= total or total <= 0:
                raise ValueError('invalid device memory observation')
        except (RuntimeError, ValueError, TypeError):
            self.memory['error_count'] += 1
            self.memory['last_probe_ok'] = False
            return
        used = total - free
        if self.memory['sample_count'] == 0:
            self.memory['first_used_bytes'] = used
        self.memory['sample_count'] += 1
        self.memory['last_probe_ok'] = True
        self.memory['last_used_bytes'] = used
        self.memory['last_total_bytes'] = total
        self.memory['sampled_max_used_bytes'] = max(
            used, self.memory['sampled_max_used_bytes'] or 0,
        )

    def summary(self):
        return {
            'cuda_counters': dict(self.counters),
            'device_memory': dict(self.memory),
            'copy_scope': 'explicit_backend_calls_only',
        }
