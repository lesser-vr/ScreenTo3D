"""Optional local oVDA integration; never bundled or selected implicitly."""
import hashlib
import importlib.util
from pathlib import Path
import sys

PROFILES = {
    (518, 686): ('db2cf668ef4347ad655983109f9e98c358d76eae9a7511a794c108b81f4d408f', 126622404),
    (518, 896): ('fbfe8fc4547ddcfb16a27fa78fe0ae1039ee2f18bb2d1ec374a280d30fa6fe99', 129065172),
    (518, 924): ('6aab5d663f544192b78a7c16d8e86c2345774602c92f93c8c1bd02376e3d410a', 129402708),
}
LICENSE_NOTICE = ('oVDA: NC-SA-UHDV1.0. Personal/non-commercial use only; '
                  'redistribution and derivatives have attribution/share-alike obligations. '
                  'Read experiments/ovda/LICENSE. No commercial use permission is implied.')


def checked_plan(directory, shape):
    directory = Path(directory).resolve(strict=True)
    path = (directory / 'model.plan').resolve(strict=True)
    digest, size = PROFILES[shape]
    if path.parent != directory or path.stat().st_size != size:
        raise ValueError('oVDA plan path/size mismatch; prepare the validated local engines')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError('oVDA plan checksum mismatch; arbitrary engine files are not accepted')
    return payload


def profiles(directory):
    if directory is None:
        raise ValueError('oVDA requires --ovda-engine-dir; use scripts/run-ovda.ps1')
    directory = Path(directory).resolve(strict=True)
    if (directory / 'model.plan').exists():
        for shape, (_, size) in PROFILES.items():
            if (directory / 'model.plan').stat().st_size == size:
                checked_plan(directory, shape)
                return {shape: directory}
        raise ValueError('Unknown oVDA plan; use the validated local engines')
    found = {}
    for shape in PROFILES:
        child = directory / f'{shape[0]}x{shape[1]}-fp32'
        if child.exists():
            child = child.resolve(strict=True)
            if child.parent != directory:
                raise ValueError('oVDA profile escapes selected directory')
            checked_plan(child, shape)
            found[shape] = child
    if not found:
        raise ValueError('No validated oVDA profiles found; see docs/product-specs/ovda-local-preview.md')
    return found


def input_shape(metadata):
    width, height = metadata.get('width'), metadata.get('height')
    if (type(width) is not int or type(height) is not int or
            not (16 <= width <= 4096 and 16 <= height <= 2160) or
            not 1.30 <= width / height <= 1.78):
        raise ValueError('oVDA supports validated landscape profiles, width 16..4096 and height 16..2160; no crop/padding fallback')
    from .vda_artifacts import profile_shape
    return profile_shape(width, height)


def runtime_class():
    # A fixed repo-relative optional package, not a plugin path supplied by users.
    root = Path(__file__).resolve().parents[2] / 'experiments' / 'ovda'
    if getattr(sys, 'frozen', False) or not (root / '__init__.py').is_file():
        raise RuntimeError('oVDA is source-app only; launch scripts/run-ovda.ps1 in the prepared repository')
    name = '_depthsbs_ovda'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, root / '__init__.py', submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    try:
        from _depthsbs_ovda.trt_engine import OvdaTrt
    except ImportError as error:
        raise RuntimeError('oVDA dependencies missing; use the prepared scripts/run-ovda.ps1 environment') from error
    return OvdaTrt


def binding(directory, runtime_dir, noncommercial=False):
    from .depth_backend import BackendBinding, BackendSpec
    if noncommercial is not True:
        raise ValueError(LICENSE_NOTICE + ' Confirm non-commercial use before conversion.')
    installed = profiles(directory)
    if runtime_dir is None or not (Path(runtime_dir) / 'nvinfer_11.dll').is_file():
        raise ValueError('oVDA requires an explicit TensorRT 11.2.1.2 runtime directory')
    selected = next(iter(installed)) if len(installed) == 1 else None
    def validate(metadata):
        nonlocal selected
        selected = None
        shape = input_shape(metadata)
        if shape not in installed:
            raise ValueError(f'No oVDA engine for {shape}; select the matching profile root')
        selected = shape
    def factory(progress):
        if selected is None:
            raise ValueError('Select oVDA profile with input preflight before engine creation')
        if progress:
            progress(dict(event='ovda_profile', input_shape=[1, 1, 3, *selected], license='NC-SA-UHDV1.0'))
        return runtime_class()(progress, directory=installed[selected], runtime_dir=runtime_dir, profile=selected)
    return BackendBinding(BackendSpec('ovda-small-c16', 'tensorrt-fp32', True, True), factory, lambda frame: frame, validate)
