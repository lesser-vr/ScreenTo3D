"""Scoped regression groups. GPU and visual acceptance are explicit, separate runs."""
import argparse
import importlib.abc
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Current-profile expectations may change with an intentional product change.
# Keep all test modules classified so additions cannot silently miss CI.
GROUPS = {'core': ['test_cleanup.py',
          'test_user_data.py',
          'test_portable_import.py',
          'test_media_process.py',
          'test_download_cache.py',
          'test_engine_reference.py',
          'test_release_packaging.py',
          'test_desktop_runtimes.py',
          'test_native_memory_contract.py',
          'test_portable_package.py',
          'test_file_interpolation.py',
          'test_messages.py',
          'test_depth_backend.py',
          'test_distill_encoder.py',
          'test_desktop_jobs.py',
          'test_file_contracts.py',
          'test_gpu_preview.py',
          'test_lifecycle.py',
          'test_local_projection.py',
          'test_output_limits.py',
          'test_pipeline_lifecycle.py',
          'test_projection_publication.py',
          'test_stereo_masks.py',
          'test_stereo_geometry.py',
          'test_stereo_stability.py',
          'test_stereo_visibility.py',
          'test_telemetry.py',
          'test_temporal_blend.py',
          'test_v1.py',
          'test_error_reporting.py'],
 'platform': ['test_stereo_layout.py',
              'test_flat_background_gpu.py',
              'test_gpu_usage.py',
              'test_static_sbs.py',
              'test_capture_boundary.py',
              'test_capture_probe_metrics.py',
              'test_capture_telemetry.py',
              'test_live_benchmark_source.py',
              'test_gpu_runtime.py',
              'test_iw3_baseline_snapshot.py',
              'test_live_device.py',
              'test_live_gpu_boundary.py',
              'test_motion_history.py',
              'test_live_host_bridge.py',
              'test_live_resolve.py',
              'test_live_reset_metrics.py',
              'test_live_sbs_boundary.py',
              'test_vfg.py',
              'test_live_source_gpu_candidate.py',
              'test_native_delivery_protocol.py',
              'test_retained_capture.py',
              'test_texture_mailbox.py'],
 'profiles': ['test_cuda_projection_owner.py',
              'test_builder_resources.py',
              'test_optional_models.py',
              'test_ovda_resolution.py',
              'test_base_trt_fp16_trial.py',
              'test_da2_base_device.py',
              'test_da2_base_input.py',
              'test_da2_base_profiles.py',
              'test_live_backend_routing.py',
              'test_live_modes.py',
              'test_ovda_binding.py',
              'test_ovda_installation.py',
              'test_padding_option.py',
              'test_presentation_policy.py',
              'test_rowflow_trust.py',
              'test_small_aspect.py',
              'test_vda_application.py',
              'test_vda_comparison.py',
              'test_vda_profiles.py'],
 'quality': ['test_benchmark_guard.py',
             'test_sbs_quality.py',
             'test_sbs_rgb_quality.py',
             'test_spring_quality.py',
             'test_depth_range.py',
             'test_uniform_background_tc.py',
             'test_depth_stage_probe.py',
             'test_distill_comparison.py',
             'test_distill_precision.py',
             'test_letterbox_refinement.py',
             'test_live_scene_history.py',
             'test_local_motion.py',
             'test_motion_ab.py',
             'test_motion_quality.py',
             'test_motion_refresh.py',
             'test_moge_motion_review.py',
             'test_nvof_probe_math.py',
             'test_offline_depth.py',
             'test_ovda_nvof_actual_skip.py',
             'test_ovda_nvof_cadence.py',
             'test_temporal_diagnostics.py',
             'test_temporal_depth_experiment.py',
             'test_quality_regression.py'],
 'qt': ['test_error_journal.py',
        'test_output_focus.py',
        'test_shortcut_help.py',
        'test_typography.py',
        'test_data_manager.py',
        'test_name_migration.py',
        'test_frame_wakeup.py',
        'test_component_setup.py',
        'test_completion_shutdown.py',
        'test_tooltips.py',
        'test_localization.py',
        'test_native_notifications.py',
        'test_output_placement.py',
        'test_window_icons.py'],
 'runtime': ['test_backend_cleanup.py',
             'test_live_model.py',
             'test_moge_adapter.py',
             'test_resource_telemetry.py',
             'test_small_gpu_input.py',
             'test_vda_device_depth.py']}


class NoGpuImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'tensorrt', 'cuda', 'torch', 'winrt'}:
            raise ImportError('CPU contracts forbid runtime import: ' + fullname)
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', action='append', choices=[*GROUPS, 'cpu', 'all'])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--resource-root', type=Path)
    args = parser.parse_args()
    selected = set()
    for group in args.group or ['core']:
        selected.update(GROUPS if group == 'all' else
                        (set(GROUPS) - {'runtime'}) if group == 'cpu' else [group])
    started = time.monotonic()
    report = dict(groups=sorted(selected), status='failed', tests=0,
                  scope='Unit/protocol and synthetic regressions; no support or visual acceptance claim')
    try:
        directory = ROOT / 'v1' / 'tests'
        found = {p.name for p in directory.glob('test_*.py')}
        listed = [name for names in GROUPS.values() for name in names]
        if len(listed) != len(set(listed)) or found != set(listed):
            raise ValueError('Test classification mismatch: ' + repr(sorted(found ^ set(listed))))
        sys.path[:0] = [str(directory), str(ROOT / 'v1'), str(ROOT)]
        if 'runtime' not in selected:
            sys.meta_path.insert(0, NoGpuImports())
        if args.resource_root:
            from screento3d_app.resources import configure_resource_root
            configure_resource_root(args.resource_root)
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for group in sorted(selected):
            for name in GROUPS[group]:
                tests = loader.loadTestsFromName(name[:-3])
                if not tests.countTestCases():
                    raise ValueError('Empty required module: ' + name)
                suite.addTests(tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        passed = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
        report.update(status='passed' if passed else 'failed', tests=result.testsRun,
                      failures=[case.id() for case, _ in result.failures],
                      errors=[case.id() for case, _ in result.errors],
                      skipped=[case.id() for case, _ in result.skipped])
    except Exception as error:
        report['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
