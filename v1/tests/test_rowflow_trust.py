import unittest
from unittest.mock import Mock, patch

from depthsbs_app import rowflow


class RowFlowTrustTests(unittest.TestCase):
    def test_changed_bridge_never_loads_native_code(self):
        with patch.object(rowflow, 'BRIDGE', Mock(read_bytes=lambda: b'untrusted fixture')), \
             patch.object(rowflow, 'BRIDGE_HASH', 'invalid'), patch.object(rowflow.ct, 'CDLL') as load:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                rowflow.bridge()
            load.assert_not_called()

    def test_changed_layout_never_loads_native_code(self):
        with patch.object(rowflow, 'LAYOUT_HASH', 'invalid'), patch.object(rowflow.ct, 'CDLL') as load:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                rowflow.bridge()
            load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
