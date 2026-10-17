"""Extract EfficientNet-B0 features for PlantVillage (raw/color) images.

Usage: python extract_features.py <plantvillage_raw_color_dir> <backbone.onnx> <out.npz> [max_per_class]
"""
import os
import random
import sys
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

from onnx_builder import preprocess

root, model_path, out_path = sys.argv[1:4]
cap = int(sys.argv[4]) if len(sys.argv) > 4 else 600
rng = random.Random(1337)

classes = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
files, labels = [], []
for ci, c in enumerate(classes):
    fs = sorted(f for f in os.listdir(os.path.join(root, c)) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    rng.shuffle(fs)
    for f in fs[:cap]:
        files.append(os.path.join(c, f))
        labels.append(ci)

opts = ort.SessionOptions()
opts.intra_op_num_threads = os.cpu_count() or 2
sess = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
feats = np.zeros((len(files), 1280), np.float32)
B = 32
t0 = time.time()
for i in range(0, len(files), B):
    batch = np.concatenate([preprocess(Image.open(os.path.join(root, f))) for f in files[i : i + B]])
    feats[i : i + B] = sess.run(["features"], {"image": batch})[0]
    if (i // B) % 50 == 0:
        print(f"{i}/{len(files)} {time.time() - t0:.0f}s", flush=True)

np.savez_compressed(out_path, features=feats, labels=np.array(labels), files=np.array(files), classes=np.array(classes))
print("done", len(files), f"{time.time() - t0:.0f}s")
