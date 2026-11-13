import unittest
from screento3d_app.portable_package import exclusion,runtime_exclusion,validate_qt_source,QT_PROFILE
import ast
from pathlib import Path
import re
import tempfile


class PortablePackageTests(unittest.TestCase):
    def test_required_qt_modules_plugins_and_fallbacks_survive(self):
        for path in ('QtOpenGL.pyd','QtNetwork.pyd','Qt6ShaderTools.dll','Qt6Core.dll',
                     'opengl32sw.dll','plugins/platforms/qwindows.dll','plugins/platforms/qoffscreen.dll',
                     'plugins/styles/qmodernwindowsstyle.dll','plugins/tls/qschannelbackend.dll',
                     'plugins/imageformats/qsvg.dll','qml/QtQuick/Controls/Basic/impl/qmldir',
                     'qml/QtQuick/Controls/Windows/qmldir','qml/QtQuick/Shapes/qmldir',
                     'qml/QtQml/WorkerScript/qmldir','qml/QtCore/qmldir',
                     'qml/QtQuick/VirtualKeyboard/Styles/qmldir','translations/qtbase_ko.qm'):
            with self.subTest(path=path):self.assertEqual(exclusion('packages/PySide6/'+path),'')
        for path in ('QtCharts.pyd','Qt6Multimedia.dll','Qt6Quick3DRuntimeRender.dll','avcodec-61.dll',
                     'qmlformat.exe','designer.exe','qml/QtCharts/qmldir','qml/QtQuick/Scene3D/qmldir',
                     'plugins/sceneparsers/gltfsceneimport.dll','plugins/sqldrivers/qsqlite.dll','typesystems/typesystem_core.xml'):
            with self.subTest(path=path):self.assertEqual(exclusion('packages/PySide6/'+path),'unused-qt')

    def test_native_tensorrt_resources_remain_and_unused_runtimes_are_separate(self):
        for name in ('nvinfer_11.dll','nvonnxparser_11.dll','nvinfer_plugin_11.dll',
                     'nvinfer_builder_resource_ptx_11.dll','nvinfer_builder_resource_sm89_11.dll','cudart64_13.dll'):
            self.assertEqual(runtime_exclusion(name),'')
        for name in ('nvinfer_lean_11.dll','nvinfer_dispatch_11.dll','nvinfer_vc_plugin_11.dll'):
            self.assertEqual(runtime_exclusion(name),'unused-tensorrt')

    def test_qt_profile_rejects_a_different_or_incomplete_sdk(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);init=root/'__init__.py';init.write_text('__version__="6.12.0"')
            with self.assertRaisesRegex(ValueError,'requires'):validate_qt_source(root)
            init.write_text('__version__="'+QT_PROFILE['pyside_version']+'"')
            with self.assertRaisesRegex(ValueError,'incomplete'):validate_qt_source(root)

    def test_profile_covers_direct_desktop_python_and_qml_imports(self):
        root=Path(__file__).resolve().parents[1]/'screento3d_app'
        for file in root.rglob('*.py'):
            for node in ast.walk(ast.parse(file.read_text(encoding='utf-8-sig'))):
                if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('PySide6.'):
                    self.assertIn(node.module.split('.')[1],QT_PROFILE['bindings'],str(file))
        for file in (root/'qml').glob('*.qml'):
            for module in re.findall(r'^import (Qt\S*)',file.read_text(encoding='utf-8'),re.M):
                self.assertNotEqual(exclusion('packages/PySide6/qml/'+module.replace('.','/')+'/qmldir'),'unused-qt',str(file))

    def test_packaged_native_and_cython_sources_are_excluded(self):
        for suffix in ('.c','.cc','.cpp','.cxx','.cu','.pyx','.pxd','.pxi','.CPP'):
            with self.subTest(suffix=suffix):
                self.assertEqual(exclusion('packages/cuda/bindings/runtime'+suffix),'development')
        for path in ('packages/cuda/bindings/runtime.cp313-win_amd64.pyd',
                     'packages/cuda/bindings/__init__.py','packages/numpy/_core/_multiarray_umath.pyd',
                     'packages/PySide6/QtCore.pyd','packages/PySide6/Qt6Core.dll',
                     'packages/PySide6/qml/QtQuick/Controls/Basic/Button.qml',
                     'packages/PySide6/qml/QtQuick/Controls/Basic/qmldir'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'')

    def test_development_files_are_excluded_without_dropping_runtime_libraries(self):
        for path in ('packages/torch/lib/dnnl.lib','packages/torch/include/ATen/a.h',
                     'packages/torch/include/README.md','packages/cuda/bindings/include/cuda.h',
                     'packages/numpy/a.hpp','packages/PySide6/a.cmake'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'development')
        for path in ('packages/torch/lib/torch_cuda.dll','packages/torch/lib/cudnn64_9.dll',
                     'packages/PySide6/Qt6Core.dll','packages/torch/_C.pyd',
                     'packages/PySide6/qml/QtQuick/Controls/Basic/qmldir'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'')

    def test_copyright_and_license_files_are_preserved(self):
        self.assertEqual(exclusion('packages/torch/include',is_dir=True),'')
        self.assertEqual(exclusion('packages/PySide6/qml/QtWebEngine',is_dir=True),'')
        for path in ('packages/torch/COPYING.LIB','packages/torch/include/LICENSE',
                     'packages/pyside6.dist-info/licenses/QtWebEngine/NOTICE',
                     'packages/cv2/NOTICE.txt','licenses/COPYRIGHT',
                     'packages/cuda/LICENSE.cpp','packages/cuda/NOTICE.pyx',
                     'packages/cuda_bindings.dist-info/licenses/copyright.c',
                     'packages/PySide6/typesystems/LICENSE.txt','packages/PySide6/plugins/multimedia/NOTICE.txt'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'')

    def test_webengine_bindings_libraries_and_resources_are_excluded(self):
        for path in ('packages/PySide6/Qt6WebEngineCore.dll','packages/PySide6/QtWebEngineCore.pyd',
                     'packages/PySide6/qml/QtWebEngine/qmldir','packages/PySide6/resources/qtwebengine_resources.pak',
                     'packages/PySide6/plugins/webview/qtwebview_webengine.dll'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'unused-webengine')

    def test_bytecode_is_excluded_and_windows_paths_are_supported(self):
        self.assertEqual(exclusion(r'packages\torch\__pycache__\x.pyc'),'bytecode')
        self.assertEqual(exclusion(r'packages\torch\lib\torch_cuda.dll'),'')

    def test_license_directory_does_not_preserve_generated_bytecode(self):
        for path in ('packages/packaging/licenses/__pycache__',
                     'packages/packaging/licenses/__pycache__/__init__.cpython-313.pyc',
                     'packages/packaging/licenses/LICENSE.pyc',
                     'packages/packaging/licenses/COPYING.pyo',
                     r'packages\packaging\licenses\__pycache__\module.pyc'):
            with self.subTest(path=path):
                self.assertEqual(exclusion(path,is_dir=path.endswith('__pycache__')),'bytecode')
        for path in ('packages/packaging/licenses/__init__.py',
                     'packages/packaging/licenses/LICENSE',
                     'packages/packaging/licenses/COPYING.LIB'):
            with self.subTest(path=path):self.assertEqual(exclusion(path),'')


if __name__=='__main__':unittest.main()
