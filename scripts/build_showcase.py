"""Extract candidate-biased windows and rescan them. Not a recall benchmark."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer
from face_watch.review_runner import run_review

ROOT = Path(__file__).resolve().parents[1]


def choose_windows(events, duration, length=24, count=2):
    starts = {max(0, min(duration-length, float(e.get('evidence_seconds', e['start_seconds']))-length/2)) for e in events}
    def score(start):
        return sum(min(length, max(1, float(e['end_seconds'])-float(e['start_seconds'])+1))
                   for e in events if start <= float(e.get('evidence_seconds', e['start_seconds'])) < start+length)
    selected = []
    for start in sorted(starts, key=lambda x: (-score(x), x)):
        if all(abs(start-other) >= length for other in selected):
            selected.append(start)
        if len(selected) == count:
            break
    return sorted(selected)


def main():
    bundle = ROOT/'showcase_bundle'
    if (bundle/'seed.json').exists():
        raise SystemExit('默认包已存在，不覆盖。正常启动无需重建。')
    bundle.mkdir(parents=True, exist_ok=True)
    state = json.loads((ROOT/'data/media_review_state.json').read_text())
    for item in state['library_items']:
        for material in item.get('materials', []):
            uri = material['local_uri']
            source = ROOT/'examples/reference.jpeg' if uri=='/demo/reference' else ROOT/'frontend_dist'/uri.lstrip('/') if uri.startswith('/assets/') else ROOT/uri.lstrip('/') if uri.startswith('/artifacts/') else Path(uri)
            relative = Path('references')/(hashlib.sha256(source.read_bytes()).hexdigest()+source.suffix)
            target = bundle/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            material['local_uri'] = '/bundled/'+relative.as_posix()
    people = []
    for person in state['library_items']:
        if person['category'] != 'person' or person['status'] == 'disabled':
            continue
        materials = [material for material in person['materials'] if material['kind'] == 'reference_image' and material.get('status') != 'disabled']
        people.append({'id':person['item_id'], 'name':person['name'],
                       'paths':[bundle/material['local_uri'].removeprefix('/bundled/') for material in materials],
                       'materials':materials, 'skip_invalid_references':True})
    people = [p for p in people if p['paths']]
    analyzer = OpenCvAnalyzer(AnalyzerConfig(detector_model=ROOT/'models/face_detection_yunet_2023mar.onnx',
        recognizer_model=ROOT/'models/face_recognition_sface_2021dec.onnx', output_dir=bundle/'evidence', detection_score_threshold=.65))
    by_asset = {}
    for task in state['review_tasks']:
        if task.get('result', {}).get('events'):
            by_asset.setdefault(task['asset_path'], []).append(task)
    tasks, catalog = [], []
    for asset, prior in sorted(by_asset.items()):
        source = Path(asset)
        if not source.is_file():
            continue
        prior = max(prior, key=lambda t: len(t['result']['events']))
        capture = cv2.VideoCapture(str(source))
        fps = capture.get(cv2.CAP_PROP_FPS)
        duration = capture.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps > 0 else 0
        capture.release()
        if duration <= 0:
            raise ValueError(f'Cannot probe {source}')
        title = '牧马人' if source.name=='sample.mp4' else source.stem.split('》')[0].lstrip('《')
        for index, start in enumerate(choose_windows(prior['result']['events'], duration), 1):
            key = hashlib.sha256(f'{source.name}:{start:.3f}'.encode()).hexdigest()[:16]
            relative = Path('clips')/f'{key}.mp4'
            video = bundle/relative
            video.parent.mkdir(exist_ok=True)
            length = min(24, duration-start)
            if not video.exists():
                temp = video.with_suffix('.partial.mp4')
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-ss', str(start), '-i', str(source), '-t', str(length), '-map', '0:v:0', '-map', '0:a:0?',
                    '-vf', "scale='min(1280,iw)':-2", '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', '-y', str(temp)], check=True)
                temp.replace(video)
            print(f'SCAN {title} {index} @{start:.1f}', flush=True)
            output = bundle/'evidence'/key
            cache = output/'result.json'
            if cache.exists():
                result = json.loads(cache.read_text())
            else:
                result = run_review(analyzer, video, people, output, lambda values: None)
                result = json.loads(json.dumps(result).replace(f'/artifacts/{key}/', f'/bundled/evidence/{key}/'))
                cache.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            task_id = 'showcase-'+key
            tasks.append({'task_id':task_id, 'name':f'{title} · 精选片段 {index}', 'asset_path':relative.as_posix(),
                'object_ids':[p['id'] for p in people], 'purpose':'validation', 'capabilities':['face'],
                'channels':{'face':'available','ocr':'not_configured','asr':'not_configured','content':'not_configured'},
                'status':'needs_review', 'progress':1, 'candidate_count':len(result['events']), 'result':result})
            catalog.append({'media_id':key, 'name':f'{title} · 片段 {index}', 'path':relative.as_posix(),
                'url':'/bundled/'+relative.as_posix(), 'duration_seconds':result['metrics']['duration_seconds'], 'film':title,
                'source_start_seconds':round(start, 2), 'task_id':task_id,
                'selection_note':'历史候选区间选取；片段已重新检查，人物身份待复核',
                'candidate_count':len(result['events'])})
            print(f'DONE {title} {index}: {len(result["events"])} candidates', flush=True)
    if not catalog:
        raise ValueError('No usable candidate windows')
    (bundle/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    (bundle/'seed.json').write_text(json.dumps({'library_items':state['library_items'], 'review_tasks':tasks}, ensure_ascii=False, indent=2))
    print(f'Bundle complete: {len(catalog)} clips, {len(people)} people', flush=True)


if __name__ == '__main__':
    main()
