"""Compile-time fix for navigation models whose map encoder overflows float16 (see fp32_map_encoder)."""


def fp32_map_encoder(runner) -> list[str]:
  """Run a navigation model's map encoder in float32 (comma's nav driving model, nav-model-integration Oct 2026).

  The model computes in float16, and the map encoder's stage 3 MLP (fc2, before its small layer scale) passes the
  float16 maximum (65504) on ordinary maps: on a NY highway route its fc2 output reached 65974 in float32. In float16
  that is inf, the next LayerNorm turns it into NaN and modeld drops the model ("external GPU model output not finite").
  comma shipped a "fix overflow inputs in map model" artifact for the same thing. Here every node that depends only on
  nav_map (and constants) is computed in float32 - its float16 weights read as float32 - and cast back to float16 where
  its result enters the rest of the model, so everything outside the map encoder is unchanged.
  Returns the boundary tensors (empty when the model has no map input)."""
  from tinygrad import dtypes
  from tinygrad.nn.onnx import OnnxNode
  if 'nav_map' not in runner.graph_inputs:
    return []
  FLOAT, FLOAT16 = 1, 10  # ONNX TensorProto data types
  consts = runner.const_names
  pure, region = {'nav_map'}, []
  half = set()  # map encoder tensors that are float16 in the model as exported
  for i, node in enumerate(runner.graph_nodes):  # topologically sorted
    ins = [x for x in node.inputs if x]
    if ins and any(x in pure for x in ins) and all(x in pure or x in consts for x in ins):
      region.append(i)
      pure.update(o for o in node.outputs if o)
      if node.op == 'Cast':
        is_half = node.opts.get('to') == FLOAT16
      else:
        is_half = any(x in half or getattr(runner.graph_values.get(x), 'dtype', None) == dtypes.half for x in ins)
      if is_half:
        half.update(o for o in node.outputs if o)
  if not region:
    return []
  in_region = set(region)
  nodes = list(runner.graph_nodes)
  for i in region:
    node = nodes[i]
    inputs = list(node.inputs)
    for k, name in enumerate(inputs):
      value = runner.graph_values.get(name)
      if name in consts and getattr(value, 'dtype', None) == dtypes.half:
        copy = name + '__f32'
        if copy not in runner.graph_values:
          runner.graph_values[copy] = value.cast(dtypes.float32)
          runner.const_names.add(copy)
        inputs[k] = copy
    opts = dict(node.opts)
    if node.op == 'Cast' and opts.get('to') == FLOAT16:
      opts['to'] = FLOAT
    nodes[i] = OnnxNode(node.op, node.opset_id, tuple(inputs), node.outputs, opts)
  # only what was float16 goes back to float16; a tensor that was float32 already (the map before its first cast, or a
  # cast to float32 inside) is left as it is
  boundary = sorted(x for x in ({x for i, node in enumerate(nodes) if i not in in_region for x in node.inputs if x in pure} |
                                {x for x in runner.graph_outputs if x in pure}) if x in half)
  # inside the map encoder a boundary tensor is renamed (float32); a cast back to float16 then makes the original name,
  # so the rest of the model (and any model output) sees what it always did
  renamed = {x: x + '__f32' for x in boundary}
  for i in region:
    node = nodes[i]
    nodes[i] = OnnxNode(node.op, node.opset_id, tuple(renamed.get(x, x) for x in node.inputs),
                        tuple(renamed.get(x, x) for x in node.outputs), node.opts)
  # each cast goes right after the node that makes its tensor: the rest of the model can use it before the map encoder
  # is finished (view_55 is read long before its last node)
  opset = nodes[region[0]].opset_id
  out = []
  for node in nodes:
    out.append(node)
    for x in boundary:
      if renamed[x] in node.outputs:
        out.append(OnnxNode('Cast', opset, (renamed[x],), (x,), {'to': FLOAT16}))
  runner.graph_nodes = tuple(out)
  return boundary
