import unittest
from types import SimpleNamespace

from distill_precision_probe import ordered_nodes


class PrecisionGraphTests(unittest.TestCase):
    def test_dependencies_are_ordered(self):
        first = SimpleNamespace(input=['input'], output=['middle'])
        second = SimpleNamespace(input=['middle'], output=['output'])
        model = SimpleNamespace(graph=SimpleNamespace(node=[second, first],
                    input=[SimpleNamespace(name='input')], initializer=[]))
        ordered_nodes(model)
        self.assertEqual(model.graph.node, [first, second])

    def test_unknown_input_is_rejected(self):
        model = SimpleNamespace(graph=SimpleNamespace(
            node=[SimpleNamespace(input=['missing'], output=['output'])],
            input=[], initializer=[]))
        with self.assertRaises(ValueError):
            ordered_nodes(model)


if __name__ == '__main__':
    unittest.main()
