"""Build an ONNX graph for EfficientNet-B0 from NumPy weights (no torch / onnx package).

Architecture follows lukemelas/EfficientNet-PyTorch (MBConv blocks, static "same" padding
for 224x224 input, BatchNorm eps=1e-3, swish activations, squeeze-excitation 0.25).
BatchNorm is folded into the preceding convolution.

Graph outputs:
  features : [N, 1280]  global-average-pooled backbone features
  logits   : [N, 1000]  ImageNet logits (used only for sanity checks)
An optional classification head (Gemm + Softmax) can be appended with `add_head`.
"""
from __future__ import annotations

import math

import numpy as np

import onnx_pb2 as P

BN_EPS = 1e-3
IMAGE_SIZE = 224

# (repeats, kernel, stride, expand, in, out)
BLOCKS = [
    (1, 3, 1, 1, 32, 16),
    (2, 3, 2, 6, 16, 24),
    (2, 5, 2, 6, 24, 40),
    (3, 3, 2, 6, 40, 80),
    (3, 5, 1, 6, 80, 112),
    (4, 5, 2, 6, 112, 192),
    (1, 3, 1, 6, 192, 320),
]


class GraphBuilder:
    def __init__(self):
        self.graph = P.GraphProto(name="agastya_crop_vision")
        self._n = 0

    def name(self, prefix):
        self._n += 1
        return f"{prefix}_{self._n}"

    def init(self, name, arr):
        arr = np.ascontiguousarray(arr)
        t = P.TensorProto(name=name)
        t.dims.extend(arr.shape)
        if arr.dtype == np.float32:
            t.data_type = P.TensorProto.FLOAT
        elif arr.dtype == np.int64:
            t.data_type = P.TensorProto.INT64
        else:
            raise TypeError(arr.dtype)
        t.raw_data = arr.tobytes()
        self.graph.initializer.append(t)
        return name

    def node(self, op, inputs, outputs=None, **attrs):
        outputs = outputs or [self.name(op.lower())]
        n = P.NodeProto(op_type=op, name=self.name("n_" + op))
        n.input.extend(inputs)
        n.output.extend(outputs)
        for k, v in attrs.items():
            a = P.AttributeProto(name=k)
            if isinstance(v, int):
                a.type = P.AttributeProto.INT
                a.i = v
            elif isinstance(v, float):
                a.type = P.AttributeProto.FLOAT
                a.f = v
            elif isinstance(v, (list, tuple)):
                a.type = P.AttributeProto.INTS
                a.ints.extend(v)
            else:
                raise TypeError(v)
            n.attribute.append(a)
        self.graph.node.append(n)
        return outputs[0]

    def value_info(self, name, shape):
        vi = P.ValueInfoProto(name=name)
        tt = vi.type.tensor_type
        tt.elem_type = P.TensorProto.FLOAT
        for d in shape:
            dim = tt.shape.dim.add()
            if isinstance(d, str):
                dim.dim_param = d
            else:
                dim.dim_value = d
        return vi


def _same_pads(size, k, s):
    out = math.ceil(size / s)
    total = max((out - 1) * s + k - size, 0)
    before = total // 2
    return before, total - before, out


def _fold_bn(w, sd, prefix, bias=None):
    gamma = sd[f"{prefix}.weight"]
    beta = sd[f"{prefix}.bias"]
    mean = sd[f"{prefix}.running_mean"]
    var = sd[f"{prefix}.running_var"]
    scale = gamma / np.sqrt(var + BN_EPS)
    w2 = (w * scale[:, None, None, None]).astype(np.float32)
    b = bias if bias is not None else np.zeros_like(mean)
    b2 = ((b - mean) * scale + beta).astype(np.float32)
    return w2, b2


def _conv(g, x, w, b, k, s, group=1, pads=None):
    wn = g.init(g.name("W"), w)
    bn = g.init(g.name("B"), b)
    pads = pads or (0, 0, 0, 0)
    return g.node("Conv", [x, wn, bn], kernel_shape=[k, k], strides=[s, s], pads=list(pads), group=group)


def _swish(g, x):
    s = g.node("Sigmoid", [x])
    return g.node("Mul", [x, s])


def build_backbone(sd) -> tuple[GraphBuilder, str, str]:
    g = GraphBuilder()
    g.graph.input.append(g.value_info("image", ["N", 3, IMAGE_SIZE, IMAGE_SIZE]))
    size = IMAGE_SIZE

    # stem
    pb, pa, size = _same_pads(size, 3, 2)
    w, b = _fold_bn(sd["_conv_stem.weight"], sd, "_bn0")
    x = _conv(g, "image", w, b, 3, 2, pads=(pb, pb, pa, pa))
    x = _swish(g, x)

    idx = 0
    for repeats, k, stride, expand, cin, cout in BLOCKS:
        for r in range(repeats):
            s = stride if r == 0 else 1
            inp = cin if r == 0 else cout
            pre = f"_blocks.{idx}"
            block_in = x
            mid = inp * expand
            if expand != 1:
                w, b = _fold_bn(sd[f"{pre}._expand_conv.weight"], sd, f"{pre}._bn0")
                x = _swish(g, _conv(g, x, w, b, 1, 1))
            pb, pa, out_size = _same_pads(size, k, s)
            w, b = _fold_bn(sd[f"{pre}._depthwise_conv.weight"], sd, f"{pre}._bn1")
            x = _swish(g, _conv(g, x, w, b, k, s, group=mid, pads=(pb, pb, pa, pa)))
            size = out_size
            # squeeze-excitation
            sq = g.node("GlobalAveragePool", [x])
            sq = _swish(g, _conv(g, sq, sd[f"{pre}._se_reduce.weight"], sd[f"{pre}._se_reduce.bias"], 1, 1))
            sq = g.node("Sigmoid", [_conv(g, sq, sd[f"{pre}._se_expand.weight"], sd[f"{pre}._se_expand.bias"], 1, 1)])
            x = g.node("Mul", [x, sq])
            w, b = _fold_bn(sd[f"{pre}._project_conv.weight"], sd, f"{pre}._bn2")
            x = _conv(g, x, w, b, 1, 1)
            if s == 1 and inp == cout:
                x = g.node("Add", [x, block_in])
            idx += 1

    w, b = _fold_bn(sd["_conv_head.weight"], sd, "_bn1")
    x = _swish(g, _conv(g, x, w, b, 1, 1))
    pooled = g.node("GlobalAveragePool", [x])
    feats = g.node("Flatten", [pooled], outputs=["features"], axis=1)
    fw = g.init("fc_W", sd["_fc.weight"].astype(np.float32))
    fb = g.init("fc_B", sd["_fc.bias"].astype(np.float32))
    logits = g.node("Gemm", [feats, fw, fb], outputs=["logits"], transB=1)
    return g, feats, logits


def add_head(g: GraphBuilder, feats: str, mean, scale, coef, intercept, prefix="head"):
    """Append standardisation + linear softmax head. coef: [C, 1280]."""
    m = g.init(f"{prefix}_mean", mean.astype(np.float32))
    sc = g.init(f"{prefix}_scale", (1.0 / scale).astype(np.float32))
    x = g.node("Sub", [feats, m])
    x = g.node("Mul", [x, sc])
    w = g.init(f"{prefix}_W", coef.astype(np.float32))
    b = g.init(f"{prefix}_B", intercept.astype(np.float32))
    z = g.node("Gemm", [x, w, b], outputs=["class_logits"], transB=1)
    return g.node("Softmax", [z], outputs=["probabilities"], axis=1)


def to_model(g: GraphBuilder, outputs: list[tuple[str, list]]) -> bytes:
    del g.graph.output[:]
    for name, shape in outputs:
        g.graph.output.append(g.value_info(name, shape))
    m = P.ModelProto(ir_version=8, producer_name="agastya-ml-training", producer_version="1")
    op = m.opset_import.add()
    op.domain = ""
    op.version = 13
    m.graph.CopyFrom(g.graph)
    return m.SerializeToString()


def preprocess(img, size=IMAGE_SIZE) -> np.ndarray:
    """PIL image -> normalised NCHW float32. Centre-square crop, bilinear resize."""
    from PIL import Image

    img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    return a.transpose(2, 0, 1)[None]
