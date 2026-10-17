"""Train and evaluate the PlantVillage classification head on frozen EfficientNet-B0 features,
then export a single ONNX model (backbone + head) plus metadata used by the AGASTYA backend.

Usage: python train_head.py <features.npz> <effb0_imagenet.pth> <out_dir> [ood_images_dir]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from onnx_builder import add_head, build_backbone, to_model
from torch_weights import load_state_dict

feat_path, weights_path, out_dir = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)
d = np.load(feat_path, allow_pickle=False)
X, y, classes = d["features"], d["labels"], [str(c) for c in d["classes"]]

X_tr, X_tmp, y_tr, y_tmp = train_test_split(X, y, test_size=0.30, stratify=y, random_state=7)
X_val, X_te, y_val, y_te = train_test_split(X_tmp, y_tmp, test_size=0.50, stratify=y_tmp, random_state=7)

scaler = StandardScaler().fit(X_tr)
best = None
for C in (0.05, 0.1, 0.3, 1.0):
    clf = LogisticRegression(C=C, max_iter=2000)
    clf.fit(scaler.transform(X_tr), y_tr)
    acc = accuracy_score(y_val, clf.predict(scaler.transform(X_val)))
    print(f"C={C} val_acc={acc:.4f}", flush=True)
    if best is None or acc > best[0]:
        best = (acc, C, clf)
val_acc, C, clf = best

P_te = clf.predict_proba(scaler.transform(X_te))
pred = P_te.argmax(1)
conf = P_te.max(1)
test_acc = accuracy_score(y_te, pred)
macro_f1 = f1_score(y_te, pred, average="macro")

# Expected calibration error (15 bins)
bins = np.linspace(0, 1, 16)
ece = 0.0
for lo, hi in zip(bins[:-1], bins[1:]):
    m = (conf > lo) & (conf <= hi)
    if m.any():
        ece += m.mean() * abs((pred[m] == y_te[m]).mean() - conf[m].mean())

thr = 0.70
cov = float((conf >= thr).mean())
acc_cov = float((pred[conf >= thr] == y_te[conf >= thr]).mean())
acc_below = float((pred[conf < thr] == y_te[conf < thr]).mean()) if (conf < thr).any() else None

# Out-of-distribution guard: cosine similarity of the (standardised) feature to the nearest class centroid.
Z_tr = scaler.transform(X_tr)
cent = np.stack([Z_tr[y_tr == c].mean(0) for c in range(len(classes))])
cent_n = cent / np.linalg.norm(cent, axis=1, keepdims=True)


def max_cos(Z):
    Zn = Z / np.linalg.norm(Z, axis=1, keepdims=True)
    return (Zn @ cent_n.T).max(1)


val_cos = max_cos(scaler.transform(X_val))
ood_threshold = float(np.percentile(val_cos, 1.0))  # 99% of in-distribution validation images pass
te_cos = max_cos(scaler.transform(X_te))
ood_pass_rate_test = float((te_cos >= ood_threshold).mean())

report = classification_report(y_te, pred, target_names=classes, output_dict=True, zero_division=0)
per_class = {c: {"precision": round(report[c]["precision"], 4), "recall": round(report[c]["recall"], 4),
                 "support": int(report[c]["support"])} for c in classes}

# Build combined ONNX model
sd = load_state_dict(weights_path)
g, feats, _logits = build_backbone(sd)
add_head(g, feats, scaler.mean_, scaler.scale_, clf.coef_, clf.intercept_)
blob = to_model(g, [("features", ["N", 1280]), ("probabilities", ["N", len(classes)])])
model_path = os.path.join(out_dir, "model.onnx")
with open(model_path, "wb") as f:
    f.write(blob)
sha = hashlib.sha256(blob).hexdigest()

np.savez_compressed(
    os.path.join(out_dir, "ood_guard.npz"),
    mean=scaler.mean_.astype(np.float32),
    scale=scaler.scale_.astype(np.float32),
    centroids=cent_n.astype(np.float32),
)

card = {
    "key": "crop-vision-plantvillage",
    "version": "1.0.0",
    "name": "Leaf condition classifier (EfficientNet-B0 features + linear head, PlantVillage)",
    "task": "single-leaf image classification (38 PlantVillage crop/condition classes)",
    "framework": "onnxruntime",
    "artifact": "model.onnx",
    "artifact_sha256": sha,
    "input": {"size": 224, "layout": "NCHW", "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
              "resize": "centre square crop, bilinear resize to 224"},
    "classes": classes,
    "backbone": {
        "architecture": "EfficientNet-B0 (ImageNet-1k pretrained, frozen)",
        "weights": "lukemelas/EfficientNet-PyTorch release 1.0, efficientnet-b0-355c32eb.pth",
        "license": "Apache-2.0",
    },
    "training_data": {
        "dataset": "PlantVillage (spMohanty/PlantVillage-Dataset, raw/color)",
        "license": "CC BY-SA 3.0",
        "citation": "Mohanty, Hughes & Salathé (2016), Frontiers in Plant Science 7:1419",
        "images_used": int(len(y)),
        "max_per_class": int(np.bincount(y).max()),
        "split": {"train": int(len(y_tr)), "validation": int(len(y_val)), "test": int(len(y_te))},
        "split_method": "stratified random split by image (seed 7)",
    },
    "head": {"type": "multinomial logistic regression on standardised features", "C": C},
    "metrics": {
        "validation_accuracy": round(float(val_acc), 4),
        "test_accuracy": round(float(test_acc), 4),
        "test_macro_f1": round(float(macro_f1), 4),
        "test_ece_15_bins": round(float(ece), 4),
        "uncertainty_threshold": thr,
        "test_coverage_at_threshold": round(cov, 4),
        "test_accuracy_at_or_above_threshold": round(acc_cov, 4),
        "test_accuracy_below_threshold": None if acc_below is None else round(acc_below, 4),
        "ood_guard_cosine_threshold": round(ood_threshold, 4),
        "ood_guard_test_pass_rate": round(ood_pass_rate_test, 4),
        "per_class": per_class,
    },
    "limitations": [
        "Trained and evaluated only on PlantVillage: single detached leaves photographed on plain backgrounds under "
        "controlled conditions. Accuracy on field photographs (multiple leaves, soil, shadows, other crops) is NOT "
        "established and is expected to be substantially lower.",
        "The random image-level split may place photographs of the same leaf in both train and test sets, so the "
        "reported test accuracy is likely optimistic.",
        "Predicts one of 38 crop/condition classes. It does not estimate disease severity, nutrient deficiency, "
        "pest species, yield impact, or recommend treatments.",
        "Crops outside the 14 PlantVillage crops are unsupported; the application reports them as unsupported input.",
    ],
    "evaluated_on": str(date.today()),
}
with open(os.path.join(out_dir, "model_card.json"), "w") as f:
    json.dump(card, f, indent=2)

print(json.dumps({k: v for k, v in card["metrics"].items() if k != "per_class"}, indent=2))
print("sha256", sha, "size", len(blob))
