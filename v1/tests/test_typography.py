"""Bundled UI fonts must survive packaging and resolve both script families."""
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QFontDatabase,QTextLayout
from screento3d_app import typography


class TypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_pinned_font_and_license_survive_portable_unicode_relocation(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('font_bundle_test',root/'scripts/build-desktop-portable.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)/'포터블 ScreenTo3D'
            fonts=stage/'v1/screento3d_app/assets/fonts'
            module.copy(typography.DIRECTORY,fonts,package_root=stage)
            manifest=typography.validate_assets(fonts)
            self.assertEqual(manifest['family'],typography.FAMILY)
            previous=QFont(self.app.font())
            try:
                with patch.object(typography,'DIRECTORY',fonts),patch.object(self.app,'_screento3d_font_id',None,create=True),patch.object(QFontDatabase,'addApplicationFont',wraps=QFontDatabase.addApplicationFont) as register:
                    self.assertEqual(typography.install(self.app),typography.FAMILY)
                    typography.install(self.app)
                    register.assert_called_once_with(str(fonts/typography.FONT_FILENAME))
                for weight in (400,500,600):
                    font=QFont(self.app.font());font.setWeight(QFont.Weight(weight))
                    layout=QTextLayout('실시간 3D · Fullscreen · 0123456789',font)
                    layout.beginLayout();line=layout.createLine();line.setLineWidth(1200);layout.endLayout()
                    families={run.rawFont().familyName() for run in layout.glyphRuns()}
                    self.assertEqual(families,{typography.FAMILY})
                    self.assertEqual({int(run.rawFont().weight()) for run in layout.glyphRuns()},{weight})
                from PySide6.QtQuick import QQuickWindow
                from screento3d_app.error_dialog import LiveErrorDialog
                owner=QQuickWindow();dialog=LiveErrorDialog(owner)
                try:
                    self.assertEqual(dialog.font().family(),typography.FAMILY)
                    self.assertEqual(dialog.text.font().family(),typography.FAMILY)
                    self.assertEqual(dialog.text.font().pixelSize(),14)
                finally:
                    dialog.deleteLater();owner.deleteLater();self.app.processEvents()
            finally:self.app.setFont(previous)

    def test_release_validation_rejects_a_modified_font_or_missing_notice(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'fonts';shutil.copytree(typography.DIRECTORY,target)
            (target/'OFL.txt').unlink()
            with self.assertRaises(FileNotFoundError):typography.validate_assets(target)
            shutil.copyfile(typography.DIRECTORY/'OFL.txt',target/'OFL.txt')
            with (target/typography.FONT_FILENAME).open('r+b') as stream:stream.write(b'bad!')
            with self.assertRaises(ValueError):typography.validate_assets(target)

    def test_missing_cosmetic_font_does_not_block_access_to_the_app(self):
        previous=QFont(self.app.font())
        try:
            with patch.object(self.app,'_screento3d_font_id',None,create=True),patch.object(QFontDatabase,'addApplicationFont',return_value=-1),patch('sys.stderr'):
                self.assertEqual(typography.install(self.app),previous.family())
                self.assertEqual(self.app.font().pixelSize(),14)
        finally:self.app.setFont(previous)
