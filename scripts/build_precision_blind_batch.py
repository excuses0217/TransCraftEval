#!/usr/bin/env python3
"""Build a shuffled, browser-playable blind-label video from rescan windows."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output/precision_first_validation/window_rescan/summary.json"
DEFAULT_OUTPUT = ROOT / "output/precision_first_validation/blind_batch"


def fit_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = frame.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized = cv2.resize(
        frame,
        (max(1, round(source_width * scale)), max(1, round(source_height * scale))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def write_resampled_clip(
    writer: cv2.VideoWriter,
    clip: Path,
    output_fps: float,
    width: int,
    height: int,
) -> int:
    capture = cv2.VideoCapture(str(clip))
    if not capture.isOpened():
        raise ValueError(f"无法打开验证片段：{clip}")
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = 25.0
    source_index = 0
    output_index = 0
    written = 0
    frame: np.ndarray | None = None
    try:
        while True:
            ok, next_frame = capture.read()
            if not ok:
                break
            frame = next_frame
            source_time = source_index / source_fps
            source_index += 1
            while output_index / output_fps <= source_time + 1e-6:
                writer.write(fit_frame(frame, width, height))
                output_index += 1
                written += 1
    finally:
        capture.release()
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=float, default=25.0)
    # Review previews include three seconds before the evidence and last up to
    # twelve seconds.  Nine seconds prevents a preview near the end of one
    # six-second sample from leaking into the next blind-label sample.
    parser.add_argument("--separator-seconds", type=float, default=9.0)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    windows = list(data["windows"])
    random.Random(args.seed).shuffle(windows)
    args.output.mkdir(parents=True, exist_ok=True)
    raw_path = args.output / "blind-label-batch.raw.mp4"
    final_path = args.output / "blind-label-batch.mp4"
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        args.fps,
        (args.width, args.height),
    )
    if not writer.isOpened():
        raise RuntimeError("无法创建盲标视频")
    separator_frames = round(args.separator_seconds * args.fps)
    separator = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    current_frame = 0
    manifest: list[dict[str, object]] = []
    try:
        for index, window in enumerate(windows, start=1):
            if current_frame:
                slate = separator.copy()
                cv2.putText(
                    slate,
                    f"CLIP {index:03d}",
                    (args.width // 2 - 95, args.height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (210, 210, 210),
                    2,
                    cv2.LINE_AA,
                )
                for _ in range(separator_frames):
                    writer.write(slate)
                current_frame += separator_frames
            start_seconds = current_frame / args.fps
            source = Path(str(window["clip_path"]))
            frames = write_resampled_clip(
                writer, source, args.fps, args.width, args.height
            )
            current_frame += frames
            manifest.append(
                {
                    "clip_id": f"clip-{index:03d}",
                    "start_seconds": round(start_seconds, 3),
                    "end_seconds": round(current_frame / args.fps, 3),
                    "source": window,
                }
            )
    finally:
        writer.release()
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(final_path),
        ],
        check=True,
    )
    raw_path.unlink()
    output = {
        "seed": args.seed,
        "video_path": str(final_path.resolve()),
        "duration_seconds": round(current_frame / args.fps, 3),
        "instruction": "标注时不得展示 source、模型分数、演员表或正负样本类型。",
        "clips": manifest,
    }
    (args.output / "private_manifest.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: output[key] for key in ("video_path", "duration_seconds")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
