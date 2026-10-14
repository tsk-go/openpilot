import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from tinygrad import Tensor, dtypes
from tinygrad.nn.onnx import OnnxRunner
from openpilot.selfdrive.modeld.map_fp32 import fp32_map_encoder


def map_model(path, map_input='nav_map'):
  """nav_map -> float16 -> a layer whose float16 result overflows before its small scale -> LayerNorm, joined with
  another input: the shape of the nav model's map encoder (stage 3 MLP fc2, layer scale, next block's norm)."""
  w = numpy_helper.from_array(np.full((4, 4), 300, np.float16), 'w')
  gamma = numpy_helper.from_array(np.full((4,), 0.01, np.float16), 'gamma')
  scale = numpy_helper.from_array(np.ones((4,), np.float16), 'scale')
  bias = numpy_helper.from_array(np.zeros((4,), np.float16), 'bias')
  nodes = [
    helper.make_node('Cast', [map_input], ['m16'], to=TensorProto.FLOAT16),
    helper.make_node('MatMul', ['m16', 'w'], ['fc2']),
    helper.make_node('Mul', ['fc2', 'gamma'], ['scaled']),
    helper.make_node('LayerNormalization', ['scaled', 'scale', 'bias'], ['feat'], axis=-1, epsilon=1e-5),
    helper.make_node('Cast', ['other'], ['o16'], to=TensorProto.FLOAT16),
    helper.make_node('Add', ['feat', 'o16'], ['joined']),
    helper.make_node('Cast', ['joined'], ['out'], to=TensorProto.FLOAT),
    # more of the map encoder after the rest of the model already used 'feat' (as view_55 in the nav model), ending in
    # a float32 output that must stay float32
    helper.make_node('Mul', ['feat', 'gamma'], ['feat2']),
    helper.make_node('Cast', ['feat2'], ['map_out'], to=TensorProto.FLOAT),
  ]
  graph = helper.make_graph(nodes, 'g',
                            [helper.make_tensor_value_info(map_input, TensorProto.FLOAT, [1, 4]),
                             helper.make_tensor_value_info('other', TensorProto.FLOAT, [1, 4])],
                            [helper.make_tensor_value_info('out', TensorProto.FLOAT, [1, 4]),
                             helper.make_tensor_value_info('map_out', TensorProto.FLOAT, [1, 4])], [w, gamma, scale, bias])
  onnx.save(helper.make_model(graph, opset_imports=[helper.make_opsetid('', 20)]), path)


def run(runner, x, name='out'):
  outs = runner({'nav_map' if 'nav_map' in runner.graph_inputs else 'map': Tensor(x), 'other': Tensor(np.ones((1, 4), np.float32))})
  return outs[name]


def test_map_encoder_overflow_fixed(tmp_path):
  path = tmp_path / 'map.onnx'
  map_model(path)
  x = np.array([[255, 0, 128, 255]], np.float32)  # 255 * 300 * 2 = 153000: past the float16 maximum
  assert not np.isfinite(run(OnnxRunner(path), x).numpy()).all()

  runner = OnnxRunner(path)
  assert fp32_map_encoder(runner) == ['feat']
  out = run(runner, x)
  scaled = (x @ np.full((4, 4), 300, np.float32)) * 0.01
  feat = (scaled - scaled.mean()) / np.sqrt(scaled.var() + 1e-5)
  np.testing.assert_allclose(out.numpy(), feat + 1, atol=1e-2)
  map_out = run(runner, x, 'map_out')
  assert map_out.dtype == dtypes.float32
  np.testing.assert_allclose(map_out.numpy(), feat * 0.01, atol=1e-3)


def test_model_without_map_untouched(tmp_path):
  path = tmp_path / 'plain.onnx'
  map_model(path, map_input='map')
  runner = OnnxRunner(path)
  nodes = runner.graph_nodes
  assert fp32_map_encoder(runner) == []
  assert runner.graph_nodes is nodes
