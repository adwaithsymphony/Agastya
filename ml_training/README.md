# Rebuilding the crop-vision model

These scripts produced `backend/ml_models/crop_vision/`. They need only numpy, Pillow, scikit-learn, onnxruntime and protobuf — no PyTorch.

1. Weights: download `efficientnet-b0-355c32eb.pth` from https://github.com/lukemelas/EfficientNet-PyTorch/releases/tag/1.0 (verify the SHA-256 starts with `355c32eb`).
2. Data: `git clone --depth 1 --filter=blob:none --sparse https://github.com/spMohanty/PlantVillage-Dataset && cd PlantVillage-Dataset && git sparse-checkout set raw/color`
3. Build the backbone ONNX (`torch_weights.py` reads the .pth without torch; `onnx_builder.py` writes the graph with the generated `onnx_pb2.py`):
   ```python
   from torch_weights import load_state_dict; from onnx_builder import build_backbone, to_model
   g, f, l = build_backbone(load_state_dict("efficientnet-b0-355c32eb.pth"))
   open("backbone.onnx", "wb").write(to_model(g, [("features", ["N", 1280]), ("logits", ["N", 1000])]))
   ```
4. `python extract_features.py PlantVillage-Dataset/raw/color backbone.onnx features.npz 600`
5. `python train_head.py features.npz efficientnet-b0-355c32eb.pth ../backend/ml_models/crop_vision`

`train_head.py` prints the metrics and writes `model.onnx`, `model_card.json` and `ood_guard.npz`.
