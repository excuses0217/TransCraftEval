# Model files

Run `scripts/download_models.sh` to download the pinned OpenCV Zoo models:

- YuNet `face_detection_yunet_2023mar.onnx` — MIT
- SFace `face_recognition_sface_2021dec.onnx` — Apache-2.0

The ONNX files are intentionally excluded from Git. The script verifies SHA-256
checksums before use.

For the encoder A/B experiment, `scripts/download_research_models.sh` downloads
InsightFace Buffalo-L and extracts `w600k_r50.onnx`.  This pretrained weight is
for non-commercial research use only.  It is suitable for local route
validation, but must not become a production dependency without separate
licensing or replacement weights.
