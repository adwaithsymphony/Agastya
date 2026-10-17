# Model cards

## crop-vision-plantvillage v1.0.0

| | |
|---|---|
| Task | Single-leaf image classification into 38 PlantVillage crop/condition classes (14 crops) |
| Architecture | EfficientNet-B0 (ImageNet-1k pretrained, frozen) → standardised 1280-d features → multinomial logistic regression |
| Backbone weights | lukemelas/EfficientNet-PyTorch release 1.0, `efficientnet-b0-355c32eb.pth` (Apache-2.0), converted to ONNX without modification |
| Training data | PlantVillage `raw/color` (spMohanty/PlantVillage-Dataset, CC BY-SA 3.0), up to 600 images per class, 20,923 images |
| Split | Stratified random by image: 14,646 train / 3,138 validation / 3,139 test (seed 7) |
| Runtime | onnxruntime CPU, ~10–20 ms per image; artifact `backend/ml_models/crop_vision/model.onnx` (SHA-256 in `model_card.json`) |

### Evaluation (actually run, 2026-10-15)
| Metric | Value |
|---|---|
| Test accuracy | 97.3 % |
| Test macro F1 | 97.3 % |
| Expected calibration error (15 bins) | 0.021 |
| Coverage at confidence ≥ 0.70 | 95.1 %, with 98.9 % accuracy; below threshold 66.0 % |
| Extra check: 400 PlantVillage images never used in training/validation/test | 96.75 % accuracy |
| Backbone sanity check (ImageNet head) | cat → "Egyptian cat", coffee → "espresso", rocket → "missile" (scikit-image sample photos) |

Per-class precision/recall is in `model_card.json` and on the admin *Models* page.

### Out-of-distribution guard
Cosine similarity between the image's standardised feature vector and the nearest class centroid; threshold = 1st percentile of validation images (0.245). 98.8 % of test leaves pass. Sample non-leaf images (cat, coffee cup, astronaut, gravel, random noise) were all rejected, including noise and gravel that the classifier alone labelled "Tomato healthy" at 97 % confidence.

### How the application uses it
- Crop not covered by the model → `unsupported_input` (no reading shown).
- Image rejected by the guard → `unsupported_input`.
- Predicted crop differs from the crop cycle's crop → `uncertain`.
- Confidence < 0.70 → `uncertain`.
- Any non-healthy condition → queued for agronomist review.
- Model missing or failing → `failed`, no class and no confidence stored.
Predictions never trigger treatment recommendations or affect harvest-safety rules.

### Limitations
- Lab images only (detached leaves, plain background). Field-photo accuracy is **not established** and expected to be much lower.
- Image-level random split may leak near-duplicate photos of the same leaf between splits; reported accuracy is likely optimistic.
- No severity, nutrient deficiency, pest species or yield estimation.
- Indian field conditions, cultivars and diseases outside the 38 classes are not represented.

### Reproduce
See `ml_training/README.md`.

## Rule-based services (not ML)
- **Harvest eligibility** (`phi-1`): deterministic PHI rules — see ARCHITECTURE.md.
- **Pollination matching** (`pm-1`) and **buyer ranking** (`br-1`): transparent scoring with hard constraints; labelled as scores, never as predictions.
- No demand-forecasting or spoilage model is included: no suitable dataset was available, so urgency uses only the shelf life or deliver-by date the farmer supplies.
