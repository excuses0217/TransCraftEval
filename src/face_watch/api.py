import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Literal, Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

from .confidence import attach_event_confidence, event_confidence

WorkspacePurpose = Literal['production', 'validation']
CURRENT_ANALYSIS_PROFILE = 'track_v3_continuity'


class CreateJobRequest(BaseModel):
    video_path: Path
    reference_image_path: Path
    person_name: str
    run_async: bool = True


class LibraryMaterial(BaseModel):
    """One attributable source asset associated with an object-library item."""

    material_id: str
    kind: Literal["reference_image", "reference_video", "rule_file"]
    title: str
    local_uri: str
    quality_note: str
    status: Literal["imported", "pending_validation", "disabled"] = "imported"


class MaterialStatusUpdate(BaseModel):
    status: Literal['pending_validation', 'disabled']
    quality_note: str = Field(min_length=1,max_length=1000)


class LibraryItemCreate(BaseModel):
    """A small, local-first object-library entry for the demonstration UI.

    The entry describes a policy target.  It intentionally does not claim that
    a reference image, a word list, or a model has already been validated.
    """

    item_id: str
    category: Literal["person", "text", "content"]
    classification: str = "未分类"
    name: str
    aliases: list[str] = Field(default_factory=list)
    definition: str
    status: Literal["draft", "ready_for_material", "ready_for_validation", "active", "disabled"] = "draft"
    materials: list[LibraryMaterial] = Field(default_factory=list)


class LibraryLifecycleRequest(BaseModel):
    action: Literal['submit_for_validation', 'activate', 'disable', 'restore']
    note: str = Field(default='', max_length=1000)


class LibraryValidationDecision(BaseModel):
    decision: Literal['passed', 'failed']
    note: str = Field(min_length=1, max_length=2000)


class ReviewTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    asset_path: Path
    object_ids: list[str] = Field(min_length=1)
    purpose: WorkspacePurpose = 'validation'
    capabilities: list[Literal['face', 'ocr', 'asr', 'content']] = Field(default_factory=lambda: ['face'])


class ReviewTaskStatusUpdate(BaseModel):
    status: Literal["draft", "ready", "running", "needs_review", "completed"]


class ReviewTaskRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EvidenceReview(BaseModel):
    review_status: Literal['pending', 'confirmed', 'rejected', 'uncertain']
    note: str = Field(default='', max_length=2000)
    reason: Literal['', 'appearance', 'not_target', 'unclear', 'insufficient_context', 'other'] = ''


class TaskReopenRequest(BaseModel):
    reason: Literal['correction', 'new_evidence', 'scope_change', 'other']
    note: str = Field(min_length=1, max_length=2000)


class EventConsolidationRequest(BaseModel):
    gap_seconds: float = Field(default=4.0, ge=0, le=10)


class Analyzer(Protocol):
    def analyze(
        self,
        video_path: Path,
        reference_image_path: Path,
        person_name: str,
        on_progress: Callable[[float], None],
    ) -> list[dict[str, object]]: ...


def create_app(
    analyzer: Analyzer | None = None,
    frontend_dir: Path | None = None,
    artifact_dir: Path | None = None,
    defaults: dict[str, str] | None = None,
    demo_media: dict[str, Path] | None = None,
    state_file: Path | None = None,
    seed_state: dict | None = None,
    bundled_dir: Path | None = None,
    media_catalog: list[dict] | None = None,
    setup_enabled: bool = False,
) -> FastAPI:
    app = FastAPI(title="Media Review Agent Prototype")
    @app.middleware('http')
    async def fresh_application_files(request, call_next):
        response = await call_next(request)
        if request.url.path in ('/', '/index.html', '/app.js', '/review.js', '/onboarding.js', '/styles.css', '/review.css') or request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        elif request.url.path.startswith('/ui-assets/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response
    jobs: dict[str, dict[str, object]] = {}
    job_inputs: dict[str, CreateJobRequest] = {}
    library_items: list[dict[str, object]] = [
        {
            "item_id": "person.zhao_benshan",
            "category": "person",
            "classification": "喜剧演员",
            "name": "赵本山",
            "aliases": ["赵本山老师"],
            "definition": "已导入一张本地肖像作为候选参考素材；仍需补充多年代、多姿态图片，并以独立媒资完成阈值验证。",
            "status": "ready_for_validation",
            "materials": [
                {
                    "material_id": "ref.zhao_benshan.2011",
                    "kind": "reference_image",
                    "title": "赵本山公开肖像（2011）",
                    "local_uri": "/assets/references/zhao-benshan-wikimedia.jpg",
                    "quality_note": "322×433；仅一张现代肖像，不能单独作为正式人物库参考集。",
                    "status": "pending_validation",
                }
            ],
        },
        {
            "item_id": "person.zhu_shimao",
            "category": "person",
            "classification": "喜剧演员",
            "name": "朱时茂",
            "aliases": [],
            "definition": "已关联项目内置的本地《牧马人》Demo 与朱时茂正面参考照；可直接用于人物召回技术验证，结论仍须由人工复核。",
            "status": "ready_for_validation",
            "materials": [
                {
                    "material_id": "ref.zhu_shimao.local_demo",
                    "kind": "reference_image",
                    "title": "朱时茂正面参考照（本地 Demo）",
                    "local_uri": "/demo/reference",
                    "quality_note": "447×447；单人正面清晰照，作为《牧马人》本地 Demo 的检索参考输入。",
                    "status": "pending_validation",
                }
            ],
        },
        {
            "item_id": "person.jackie_chan",
            "category": "person",
            "classification": "影视演员",
            "name": "成龙",
            "aliases": ["Jackie Chan"],
            "definition": "已导入一张高质量近景肖像作为主参考；后续应补充目标年代、无遮挡和侧向姿态素材，再以独立媒资完成验证。",
            "status": "ready_for_validation",
            "materials": [
                {
                    "material_id": "ref.jackie_chan.locarno_2025",
                    "kind": "reference_image",
                    "title": "成龙近景肖像（2025）",
                    "local_uri": "/assets/references/jackie-chan-locarno-2025.jpg",
                    "quality_note": "856×1110；单人近景、脸部清晰，可作为当前主参考；佩戴眼镜且年龄跨度较大，仍需做跨年代阈值验证。",
                    "status": "pending_validation",
                },
            ],
        },
        {
            "item_id": "person.gong_li",
            "category": "person",
            "classification": "影视演员",
            "name": "巩俐",
            "aliases": ["Gong Li"],
            "definition": "已导入一张肖像作为候选参考素材；需补充更多姿态和年代的本地素材后再进行人脸检索验证。",
            "status": "ready_for_validation",
            "materials": [
                {
                    "material_id": "ref.gong_li.cannes_2007",
                    "kind": "reference_image",
                    "title": "Gong Li Cannes（2007）",
                    "local_uri": "/assets/references/gong-li-cannes-wikimedia.jpg",
                    "quality_note": "400×544；清晰度有限，仅适合作为素材管理演示与补充参考。",
                    "status": "pending_validation",
                }
            ],
        },
        {
            "item_id": "text.seed_terms",
            "category": "text",
            "classification": "外部词表种子",
            "name": "敏感词种子库",
            "aliases": ["OCR", "ASR"],
            "definition": "外部开源词表仅作为待治理种子；需映射为内部规则、版本与确认条件。",
            "status": "draft",
            "materials": [],
        },
        {
            "item_id": "content.visual_context",
            "category": "content",
            "classification": "视觉语义规则",
            "name": "视觉内容候选",
            "aliases": ["场景", "对象", "行为"],
            "definition": "Chinese-CLIP 等模型只生成候选；必须结合其他证据与人工复核。",
            "status": "draft",
            "materials": [],
        },
    ]
    review_tasks: list[dict[str, object]] = []
    state_lock = Lock()

    saved_library = None
    managed_media = deepcopy(media_catalog or [])
    workspace_initialized = not setup_enabled
    if seed_state is not None:
        library_items = deepcopy(seed_state['library_items'])
        saved_library = deepcopy(library_items)
        review_tasks = deepcopy(seed_state['review_tasks'])
    if state_file is not None and state_file.is_file():
        try:
            saved_state = json.loads(state_file.read_text(encoding="utf-8"))
            library_items = saved_state.get("library_items", library_items)
            saved_library = deepcopy(library_items)
            review_tasks = saved_state.get("review_tasks", review_tasks)
            managed_media = saved_state.get('media_items', managed_media)
            workspace_initialized = saved_state.get('workspace_initialized', True)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError('审核数据读取失败；保留原文件，停止启动以避免覆盖。') from exc

    catalog_by_id = {m.get('media_id'):m for m in (media_catalog or [])}
    for media in managed_media:
        original = catalog_by_id.get(media.get('media_id'))
        if original and original.get('path')==media.get('path') and original.get('sha256'):
            media.setdefault('sha256', original['sha256'])

    def merge_seed_material(item_id: str, seed_material: dict[str, object]) -> None:
        item = next((item for item in library_items if item["item_id"] == item_id), None)
        if item is None:
            return
        materials = item.setdefault("materials", [])
        if not any(material["material_id"] == seed_material["material_id"] for material in materials):
            materials.append(seed_material)

    for item in library_items:
        item["materials"] = [material for material in item.get("materials", []) if material.get("local_uri")]
        for material in item["materials"]:
            material.pop("source_url", None)
            material.pop("license", None)
            material.pop("attribution", None)

    item_definitions = {
        "person.zhao_benshan": "已导入一张本地肖像作为候选参考素材；仍需补充多年代、多姿态图片，并以独立媒资完成阈值验证。",
        "person.gong_li": "已导入一张肖像作为候选参考素材；需补充更多姿态和年代的本地素材后再进行人脸检索验证。",
    }
    for item in library_items:
        if item["item_id"] in item_definitions:
            item["definition"] = item_definitions[item["item_id"]]

    jackie_item = next((item for item in library_items if item["item_id"] == "person.jackie_chan"), None)
    if jackie_item is not None:
        jackie_item["definition"] = "已导入三张清晰的本地近景肖像，覆盖不同年份与造型；作为候选参考集，仍须通过独立媒资验证后方可用于正式审核。"
        jackie_item["status"] = "ready_for_validation"
        for jackie_material in [
            {
                "material_id": "ref.jackie_chan.2007",
                "kind": "reference_image",
                "title": "成龙肖像（2007）",
                "local_uri": "/assets/references/jackie-chan-2007-wikimedia.jpg",
                "quality_note": "清晰近景，作为较早时期的补充参考。",
                "status": "pending_validation",
            },
            {
                "material_id": "ref.jackie_chan.2016",
                "kind": "reference_image",
                "title": "成龙肖像（2016）",
                "local_uri": "/assets/references/jackie-chan-2016-wikimedia.jpg",
                "quality_note": "清晰近景，补充不同造型。",
                "status": "pending_validation",
            },
            {
                "material_id": "ref.jackie_chan.locarno_2025",
                "kind": "reference_image",
                "title": "成龙近景肖像（2025）",
                "local_uri": "/assets/references/jackie-chan-locarno-2025.jpg",
                "quality_note": "清晰近景，补充近期形象。",
                "status": "pending_validation",
            },
        ]:
            merge_seed_material("person.jackie_chan", jackie_material)

    zhu_item = next((item for item in library_items if item["item_id"] == "person.zhu_shimao"), None)
    if zhu_item is not None:
        zhu_item["definition"] = "已关联本地《牧马人》Demo 与两张清晰、造型不同的朱时茂参考照，可用于人物召回技术验证；结论仍须由人工复核。"
        zhu_item["status"] = "ready_for_validation"
        merge_seed_material(
            "person.zhu_shimao",
            {
                "material_id": "ref.zhu_shimao.local_demo",
                "kind": "reference_image",
                "title": "朱时茂正面参考照（本地 Demo）",
                "local_uri": "/demo/reference",
                "quality_note": "447×447；单人正面清晰照，作为《牧马人》本地 Demo 的检索参考输入。",
                "status": "pending_validation",
            },
        )
        merge_seed_material(
            "person.zhu_shimao",
            {
                "material_id": "ref.zhu_shimao.1980s",
                "kind": "reference_image",
                "title": "朱时茂早期影视肖像",
                "local_uri": "/assets/references/zhu-shimao-1980s.jpg",
                "quality_note": "清晰近景，补充早期影视造型。",
                "status": "pending_validation",
            },
        )

    for gong_material in [
        {
            "material_id": "ref.gong_li.2013",
            "kind": "reference_image",
            "title": "巩俐肖像（2013）",
            "local_uri": "/assets/references/gong-li-2013-wikimedia.jpg",
            "quality_note": "高分辨率近景，作为主参考图。",
            "status": "pending_validation",
        },
        {
            "material_id": "ref.gong_li.cannes_2011_1",
            "kind": "reference_image",
            "title": "巩俐戛纳近景（2011）",
            "local_uri": "/assets/references/gong-li-cannes-2011-wikimedia.jpg",
            "quality_note": "509×720；正面近景，脸部清晰，适合作为本地参考集中的主视角素材。",
            "status": "pending_validation",
        },
        {
            "material_id": "ref.gong_li.cannes_2011_2",
            "kind": "reference_image",
            "title": "巩俐戛纳近景（2011，视角二）",
            "local_uri": "/assets/references/gong-li-cannes-2011-2-wikimedia.jpg",
            "quality_note": "508×720；近正面视角，与主视角素材互补；仍需结合独立媒资做阈值验证。",
            "status": "pending_validation",
        },
    ]:
        merge_seed_material("person.gong_li", gong_material)

    # Seeds initialize a new workspace only, never mutate persisted user edits.
    if saved_library is not None:
        library_items = saved_library
    for task in review_tasks:
        task.setdefault('purpose', 'validation')
        task.setdefault('capabilities', ['face'])

    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def usable_reference_count(item: dict[str, object]) -> int:
        return sum(
            material.get('kind') == 'reference_image' and material.get('status') != 'disabled'
            for material in item.get('materials', [])
        )

    def object_validation(item: dict[str, object]) -> dict[str, object]:
        validation = item.setdefault('validation', {})
        validation.setdefault('status', 'not_started')
        validation.setdefault('note', '')
        validation.setdefault('decided_at', None)
        return validation

    def append_lifecycle(item: dict[str, object], event: str, note: str = '') -> None:
        history = item.setdefault('lifecycle_history', [])
        history.append({'at': now_iso(), 'actor': '本地管理员', 'event': event, 'note': note})

    def normalize_library_item(item: dict[str, object]) -> None:
        item.setdefault('lifecycle_history', [])
        object_validation(item)

    def invalidate_object_validation(item: dict[str, object], note: str) -> None:
        if item.get('category') != 'person':
            return
        validation = object_validation(item)
        if validation.get('status') == 'passed' or item.get('status') == 'active':
            validation.update(status='not_started', note='', decided_at=None)
            if item.get('status') == 'active':
                item['status'] = 'ready_for_validation'
            append_lifecycle(item, 'validation_invalidated', note)

    for item in library_items:
        normalize_library_item(item)

    def validate_scope(request):
        if not request.name.strip():
            raise HTTPException(422, '请输入任务名称')
        if not request.asset_path.is_file() or request.asset_path.suffix.lower() not in {'.mp4','.mkv','.mov','.avi','.ts','.m4v','.webm','.mpeg','.mpg'}:
            raise HTTPException(422, '请选择存在的本地视频文件')
        if request.capabilities != ['face']:
            raise HTTPException(422, '当前仅启用人物画面检查；文字、语音和内容检查暂未启用')
        for key in request.object_ids:
            item = next((i for i in library_items if i['item_id'] == key), None)
            if item is None or item['category'] != 'person':
                raise HTTPException(422, '当前任务只能选择人物对象')
            if item['status'] == 'disabled' or (request.purpose == 'production' and item['status'] != 'active'):
                raise HTTPException(422, f"{item['name']}尚未启用，不能用于生产审核；请先在算法验证中确认")
            if request.purpose == 'production' and object_validation(item).get('status') != 'passed':
                raise HTTPException(422, f"{item['name']}尚未完成可追溯的验证确认，不能用于生产审核")
            if not any(m['kind'] == 'reference_image' and m.get('status')!='disabled' for m in item.get('materials', [])):
                raise HTTPException(422, f"{item['name']}缺少参考照片")

    def persist_state() -> None:
        if state_file is None:
            return
        state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = state_file.with_suffix(".tmp")
        temporary_file.write_text(
            json.dumps(
                {"library_items": library_items, "review_tasks": review_tasks,
                 'media_items': managed_media, 'workspace_initialized': workspace_initialized},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_file.replace(state_file)

    persist_state()

    # A process restart cannot resume a daemon worker; preserve its partial status.
    for task in review_tasks:
        if task['status'] == 'running':
            task.update(status='failed', error='服务重启中断了分析，请重新执行。')
    persist_state()

    def find_task(task_id):
        task = next((t for t in review_tasks if t['task_id'] == task_id), None)
        if task is None:
            raise HTTPException(404, 'review task not found')
        return task

    def present_task(task: dict[str, object]) -> dict[str, object]:
        """Return current-algorithm confidence without adapting legacy runs."""
        presented = deepcopy(task)
        result = presented.get('result') or {}
        if result and presented.get('analysis_profile') != CURRENT_ANALYSIS_PROFILE:
            result['confidence_available'] = False
            result['confidence_unavailable_reason'] = '该任务由旧版算法生成，请使用当前算法重新检查。'
            for event in result.get('events', []):
                for key in tuple(event):
                    if key.startswith('confidence_'):
                        event.pop(key, None)
            return presented
        reference_counts = {
            item.get('person_id'): int(item.get('reference_count') or 0)
            for item in result.get('reference_snapshot', [])
        }
        for event in result.get('events', []):
            event.setdefault('reference_count', reference_counts.get(event.get('person_id'), 0))
            attach_event_confidence(event)
        if result:
            result['confidence_available'] = True
            result.pop('confidence_unavailable_reason', None)
            library_names = {item.get('item_id'): item.get('name') for item in library_items}
            snapshot_names = {
                item.get('person_id'): item.get('name')
                for item in result.get('reference_snapshot', [])
            }
            event_names = {
                event.get('person_id'): event.get('person_name')
                for event in result.get('events', [])
            }
            summaries = []
            coverage_complete = result.get('metrics', {}).get('coverage_complete') is not False
            for object_id in presented.get('object_ids', []):
                events = [
                    event for event in result.get('events', [])
                    if event.get('person_id') == object_id
                ]
                confirmed = sum(event.get('review_status', 'pending') == 'confirmed' for event in events)
                rejected = sum(event.get('review_status', 'pending') == 'rejected' for event in events)
                unresolved = len(events) - confirmed - rejected
                if confirmed:
                    conclusion = 'confirmed'
                elif unresolved:
                    conclusion = 'unresolved'
                elif not coverage_complete:
                    conclusion = 'incomplete'
                elif events:
                    conclusion = 'excluded'
                else:
                    conclusion = 'not_found'
                summaries.append({
                    'object_id': object_id,
                    'name': library_names.get(object_id) or snapshot_names.get(object_id) or event_names.get(object_id) or '未知人物',
                    'candidate_count': len(events),
                    'confirmed': confirmed,
                    'rejected': rejected,
                    'unresolved': unresolved,
                    'conclusion': conclusion,
                })
            result['object_summaries'] = summaries
        return presented

    def append_task_history(task: dict[str, object], event: str, **details: object) -> None:
        task.setdefault('audit_history', []).append({'at': now_iso(), 'actor': '本地管理员', 'event': event, **details})

    def snapshot_completed_result(task: dict[str, object], completed_at: str) -> int:
        version = len(task.setdefault('audit_versions', [])) + 1
        task['audit_versions'].append({
            'version': version,
            'completed_at': completed_at,
            'purpose': task.get('purpose', 'validation'),
            'events': deepcopy((task.get('result') or {}).get('events', [])),
            'metrics': deepcopy((task.get('result') or {}).get('metrics', {})),
        })
        task['audit_version'] = version
        return version

    # A fully covered run with no candidates is already a machine conclusion,
    # not work for a human reviewer. Finalize previously persisted runs once so
    # old local data follows the same state machine as newly executed tasks.
    finalized_zero_candidate_task = False
    for task in review_tasks:
        result = task.get('result') or {}
        if (
            task.get('status') == 'needs_review'
            and not result.get('events')
            and result.get('metrics', {}).get('coverage_complete') is True
        ):
            completed_at = task.get('analysis_completed_at') or now_iso()
            version = snapshot_completed_result(task, completed_at)
            task.update(status='completed', completed_at=completed_at, candidate_count=0)
            append_task_history(task, 'auto_completed_no_findings', version=version)
            finalized_zero_candidate_task = True
    if finalized_zero_candidate_task:
        persist_state()

    @app.get('/api/review-tasks/{task_id}')
    def task_detail(task_id: str):
        with state_lock:
            return present_task(find_task(task_id))

    @app.get('/api/review-tasks/{task_id}/video')
    def task_video(task_id: str):
        path = Path(find_task(task_id)['asset_path'])
        if not path.is_file():
            raise HTTPException(404, '本地媒资已不存在')
        return FileResponse(path)

    @app.get('/api/review-tasks/{task_id}/report')
    def task_report(task_id: str):
        from html import escape
        with state_lock:
            task = present_task(find_task(task_id))
        if not task.get('result'):
            raise HTTPException(409, '任务尚未生成结果')
        labels = {'pending':'未处理','confirmed':'确认出现','rejected':'已排除','uncertain':'留待复核'}
        reasons = {'appearance':'人工对照确认','not_target':'不是目标人物','unclear':'画面不清楚','insufficient_context':'需要更多上下文','other':'其他','':''}
        rows = []
        confidence_available = (task.get('result') or {}).get('confidence_available') is True
        for index,event in enumerate(task['result']['events'],1):
            seconds = int(event['start_seconds'])
            at = f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
            note='；'.join(filter(None,[reasons.get(event.get('reason',''),''),event.get('note','')]))
            confidence_text = '不可用'
            if confidence_available:
                confidence = event_confidence(event)
                confidence_label = {'high':'较高','medium':'中等','low':'较低'}[confidence['confidence_level']]
                confidence_text = f"{confidence_label}（证据指数 {confidence['confidence_score']}/100）"
            rows.append(f"<tr><td>{index}</td><td>{escape(event['person_name'])}</td><td>{at}</td><td>{confidence_text}</td><td>{labels.get(event.get('review_status','pending'),'未处理')}</td><td>{escape(note)}</td></tr>")
        conclusion_labels = {
            'confirmed': '确认出现',
            'excluded': '候选均已排除',
            'not_found': '系统未发现',
            'unresolved': '尚未完成',
            'incomplete': '覆盖不完整',
        }
        summary_rows = ''.join(
            '<tr>'
            f"<td>{escape(summary['name'])}</td>"
            f"<td>{summary['candidate_count']}</td>"
            f"<td>{summary['confirmed']}</td>"
            f"<td>{summary['rejected']}</td>"
            f"<td>{escape(conclusion_labels.get(summary['conclusion'], '待确认'))}</td>"
            '</tr>'
            for summary in task['result'].get('object_summaries', [])
        )
        scope = '历史抽检记录，仅针对本次提供的画面。' if task.get('import_key') else '本次审核范围：人物出镜。文字、声音和剧情内容不在本次范围内。'
        document = '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><title>审核记录</title><style>body{font:15px sans-serif;max-width:1000px;margin:40px auto;color:#253333}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:12px;text-align:left}</style>'
        document += f"<h1>{escape(task['name'])}</h1><p>{escape(Path(task['asset_path']).name)}</p><p>{scope}</p><p>审核状态：{'已完成' if task['status']=='completed' else '尚未完成'}</p><p>导出时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}</p>"
        document += '<p>用途：'+('生产审核' if task.get('purpose')=='production' else '算法验证，非正式审核结论')+'</p>'
        document += '<p>'+('证据指数综合多帧稳定性、模型判断、画面环境和参考覆盖生成，不是人物身份概率。' if confidence_available else escape(task['result'].get('confidence_unavailable_reason','旧版任务不提供当前证据指数。')))+'</p>'
        document += '<h2>人物审核结论</h2><table><thead><tr><th>核查人物</th><th>候选片段</th><th>确认出现</th><th>已排除</th><th>结论</th></tr></thead><tbody>'+summary_rows+'</tbody></table>'
        document += '<h2>候选片段处理记录</h2><table><thead><tr><th>序号</th><th>核查人物</th><th>片段位置</th><th>综合证据</th><th>处理结果</th><th>备注</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></html>'
        return Response(document, media_type='text/html', headers={'Content-Disposition':f'attachment; filename="review-{task_id}.html"'})

    preview_lock = Lock()

    @app.post('/api/review-tasks/{task_id}/events/{event_id}/preview')
    def preview_event(task_id: str, event_id: str):
        import hashlib
        import subprocess
        import tempfile
        with state_lock:
            task = deepcopy(find_task(task_id))
        event = next((e for e in (task.get('result') or {}).get('events', []) if e['event_id'] == event_id), None)
        if event is None:
            raise HTTPException(404, '片段不存在')
        source = Path(task['asset_path'])
        if artifact_dir is None or not source.is_file():
            raise HTTPException(404, '本地媒资或预览存储不可用')
        event_start = float(event.get('start_seconds', 0))
        event_end = float(event.get('end_seconds', event_start))
        start=max(0, event_start-2)
        duration=min(30, max(8, event_end-event_start+4))
        key=hashlib.sha256(f'{source.resolve()}:{source.stat().st_mtime_ns}:{source.stat().st_size}:{start}:{duration}:v2'.encode()).hexdigest()
        folder=artifact_dir/'previews'
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/f'{key}.mp4'
        if not output.is_file():
            if not preview_lock.acquire(blocking=False):
                raise HTTPException(409, '正在准备其他预览，请稍后再试')
            temporary=None
            try:
                import imageio_ffmpeg
                with tempfile.NamedTemporaryFile(suffix='.mp4',dir=folder,delete=False) as f:
                    temporary=Path(f.name)
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-y','-ss',str(start),'-i',str(source),'-t',str(duration),'-map','0:v:0','-map','0:a:0?','-vf','scale=960:-2','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(temporary)],capture_output=True,check=True,timeout=60)
                temporary.replace(output)
            except (ImportError,RuntimeError,subprocess.SubprocessError,OSError) as exc:
                raise HTTPException(503, '片段预览生成失败，请查看静帧或留待复核') from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                preview_lock.release()
        actual_duration = duration
        try:
            import cv2
            capture = cv2.VideoCapture(str(output))
            output_fps = capture.get(cv2.CAP_PROP_FPS)
            output_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            capture.release()
            if output_fps > 0 and output_frames > 0:
                actual_duration = output_frames / output_fps
        except (ImportError, RuntimeError, OSError):
            pass
        return {'url':f'/artifacts/previews/{key}.mp4','start_seconds':start,'duration_seconds':round(actual_duration, 2)}

    @app.post('/api/review-tasks/{task_id}/complete')
    def complete_task(task_id: str):
        with state_lock:
            task = find_task(task_id)
            result = task.get('result')
            if task['status'] == 'running' or result is None:
                raise HTTPException(409, '请等待分析完成')
            if task['status'] == 'completed':
                raise HTTPException(409, '审核已完成；如需修改，请先填写原因重新打开审核')
            if any(e.get('review_status', 'pending') in ('pending', 'uncertain') for e in result['events']):
                raise HTTPException(409, '仍有待复核或无法判定的候选，请先处理')
            if result.get('metrics', {}).get('coverage_complete') is False:
                raise HTTPException(409, '扫描覆盖不完整，不能完成任务')
            completed_at = now_iso()
            version = snapshot_completed_result(task, completed_at)
            task.update(status='completed', completed_at=completed_at)
            append_task_history(task, 'completed', version=version)
            persist_state()
            return present_task(task)

    @app.post('/api/review-tasks/{task_id}/reopen')
    def reopen_task(task_id: str, request: TaskReopenRequest):
        with state_lock:
            task = find_task(task_id)
            if task.get('status') != 'completed':
                raise HTTPException(409, '只有已完成的审核可以重新打开')
            completed_at = task.get('completed_at')
            task['last_completed_at'] = completed_at
            task.pop('completed_at', None)
            task.update(status='needs_review', reopened_at=now_iso())
            append_task_history(task, 'reopened', reason=request.reason, note=request.note, previous_completed_at=completed_at)
            persist_state()
            return present_task(task)

    @app.patch('/api/review-tasks/{task_id}/events/{event_id}')
    def review_event(task_id: str, event_id: str, request: EvidenceReview):
        with state_lock:
            task = find_task(task_id)
            if task['status'] == 'running':
                raise HTTPException(409, '任务执行中')
            if task['status'] == 'completed':
                raise HTTPException(409, '审核已完成；请先填写原因重新打开审核')
            event = next((e for e in task.get('result', {}).get('events', []) if e['event_id'] == event_id), None)
            if event is None:
                raise HTTPException(404, 'event not found')
            event.setdefault('history', []).append({'at': datetime.now(timezone.utc).isoformat(), 'previous': event.get('review_status', 'pending'), **request.model_dump()})
            event.update(request.model_dump())
            task['status'] = 'needs_review'
            append_task_history(task, 'event_reviewed', event_id=event_id, review_status=request.review_status)
            persist_state()
            return present_task(task)

    @app.post('/api/review-tasks/{task_id}/consolidate-events')
    def consolidate_task_events(task_id: str, request: EventConsolidationRequest):
        """Regroup a pre-existing task after the event grouping policy changes."""
        from .review_runner import consolidate_review_events
        with state_lock:
            task = find_task(task_id)
            if task['status'] in ('running', 'completed'):
                raise HTTPException(409, '执行中或已归档的任务不能重新归并片段')
            result = task.get('result')
            if result is None:
                raise HTTPException(409, '任务尚未生成结果')
            before = len(result.get('events', []))
            result['events'] = consolidate_review_events(
                result.get('events', []), request.gap_seconds
            )
            after = len(result['events'])
            result.setdefault('metrics', {})['raw_review_events'] = before
            result['metrics']['review_events'] = after
            result['metrics']['event_merge_gap_seconds'] = request.gap_seconds
            task['candidate_count'] = after
            append_task_history(
                task,
                'events_consolidated',
                before=before,
                after=after,
                gap_seconds=request.gap_seconds,
            )
            persist_state()
            return present_task(task)

    @app.post('/api/review-tasks/{task_id}/run', status_code=202)
    def execute_task(task_id: str):
        if analyzer is None or not hasattr(analyzer, '_analysis_lock') or artifact_dir is None:
            raise HTTPException(503, '多人物分析器未配置')
        with state_lock:
            task = find_task(task_id)
            if any(t['status'] == 'running' for t in review_tasks):
                raise HTTPException(409, '已有分析任务执行中，请等待完成')
            if task.get('result'):
                raise HTTPException(409, '此任务已有结果，请新建任务进行对比，保留原复核记录')
            validate_scope(ReviewTaskCreate(**task))
            people = []
            for object_id in task['object_ids']:
                item = next(i for i in library_items if i['item_id'] == object_id)
                if item['category'] != 'person':
                    continue
                paths = []
                usable_materials = []
                for material in item['materials']:
                    if material['kind'] != 'reference_image' or material.get('status')=='disabled':
                        continue
                    uri = material['local_uri']
                    if uri == '/demo/reference':
                        path = (demo_media or {}).get('reference')
                    elif uri.startswith('/assets/') and frontend_dir:
                        path = (frontend_dir / uri.lstrip('/')).resolve()
                        if not path.is_relative_to(frontend_dir.resolve()):
                            raise HTTPException(422, '参考图路径无效')
                    elif uri.startswith('/artifacts/'):
                        path = (artifact_dir / uri[len('/artifacts/'):]).resolve()
                        if not path.is_relative_to(artifact_dir.resolve()):
                            raise HTTPException(422, '参考图路径无效')
                    elif uri.startswith('/bundled/') and bundled_dir:
                        path = (bundled_dir / uri[len('/bundled/'):]).resolve()
                        if not path.is_relative_to(bundled_dir.resolve()):
                            raise HTTPException(422, '参考图路径无效')
                    else:
                        path = Path(uri)
                    if path is None or not path.is_file():
                        raise HTTPException(422, f"{item['name']}的参考图不存在")
                    paths.append(path)
                    usable_materials.append(deepcopy(material))
                if not paths:
                    raise HTTPException(422, f"{item['name']}缺少本地参考图")
                people.append({'id': item['item_id'], 'name': item['name'], 'paths': paths, 'materials': usable_materials, 'skip_invalid_references': task.get('purpose') == 'validation'})
            if not people:
                raise HTTPException(422, '请关联至少一个具有参考图的人物对象')
            if not Path(task['asset_path']).is_file():
                raise HTTPException(422, '本地媒资不存在')
            task.update(
                analysis_profile=CURRENT_ANALYSIS_PROFILE,
                status='running',
                progress=0,
                error=None,
                run_id=uuid4().hex,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            persist_state()
            initial = deepcopy(task)

        def worker():
            def report(values):
                with state_lock:
                    task.update(values)
            try:
                with analyzer._analysis_lock:
                    import cv2
                    from .video_track_runner import RECALL_TRACK_POLICY, run_track_review
                    source = cv2.VideoCapture(str(task['asset_path']))
                    source_fps = source.get(cv2.CAP_PROP_FPS)
                    source_frames = source.get(cv2.CAP_PROP_FRAME_COUNT)
                    source.release()
                    source_duration = source_frames/source_fps if source_fps > 0 else 0
                    # Dense sampling for short validation clips; one sample
                    # per second for long-form media keeps full-film jobs
                    # operational while preserving multi-frame tracks.
                    track_interval = 1.0 if source_duration >= 900 else .5
                    result = run_track_review(
                        analyzer,
                        Path(task['asset_path']),
                        people,
                        artifact_dir / task['run_id'],
                        report,
                        interval=track_interval,
                        policy=RECALL_TRACK_POLICY,
                    )
                result['analysis_profile'] = CURRENT_ANALYSIS_PROFILE
                with state_lock:
                    analyzed_at = datetime.now(timezone.utc).isoformat()
                    task.update(
                        result=result,
                        progress=1,
                        candidate_count=len(result['events']),
                        analysis_completed_at=analyzed_at,
                    )
                    if result['events']:
                        task.update(status='needs_review')
                    elif result.get('metrics', {}).get('coverage_complete') is False:
                        task.update(status='failed', error='视频扫描覆盖不完整，请重新检查。', failed_at=analyzed_at)
                    else:
                        version = snapshot_completed_result(task, analyzed_at)
                        task.update(status='completed', completed_at=analyzed_at)
                        append_task_history(task, 'auto_completed_no_findings', version=version)
                    persist_state()
            except Exception as exc:
                with state_lock:
                    task.update(status='failed', error=str(exc), failed_at=datetime.now(timezone.utc).isoformat())
                    persist_state()
        Thread(target=worker, daemon=True).start()
        return initial

    @app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(request: CreateJobRequest) -> dict[str, str]:
        if not request.video_path.is_file():
            raise HTTPException(status_code=422, detail="video_path does not exist")
        if not request.reference_image_path.is_file():
            raise HTTPException(status_code=422, detail="reference_image_path does not exist")
        job_id = uuid4().hex
        job = {
            "job_id": job_id,
            "status": "queued",
            "person_name": request.person_name,
            "progress": 0.0,
            "events": [],
            "error": None,
        }
        jobs[job_id] = job
        job_inputs[job_id] = request
        if request.run_async and analyzer is not None:
            def execute_async() -> None:
                job["status"] = "running"

                def on_progress(value: float) -> None:
                    job["progress"] = max(0.0, min(1.0, value))

                try:
                    job["events"] = analyzer.analyze(
                        request.video_path,
                        request.reference_image_path,
                        request.person_name,
                        on_progress,
                    )
                    job["progress"] = 1.0
                    job["status"] = "completed"
                except Exception as exc:
                    job["status"] = "failed"
                    job["error"] = str(exc)

            Thread(target=execute_async, daemon=True).start()
        return {
            "job_id": job_id,
            "status": "queued",
            "person_name": request.person_name,
        }

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/api/settings")
    def get_settings() -> dict[str, str]:
        return defaults or {}

    @app.get('/api/local-media')
    def local_media():
        import hashlib
        if media_catalog is not None or setup_enabled:
            return deepcopy(managed_media)
        paths = set()
        if frontend_dir is not None:
            root = frontend_dir.resolve().parent
            for folder in (root/'媒资', root/'examples'):
                if folder.is_dir():
                    paths.update(p.resolve() for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.mp4','.ts','.mkv','.mov','.webm'))
        paths.update(Path(t['asset_path']) for t in review_tasks if t.get('asset_path') and Path(t['asset_path']).is_file())
        known = {m['path'] for m in managed_media}
        return deepcopy(managed_media) + [
            {
                'media_id': 'local-'+hashlib.sha256(str(p).encode()).hexdigest()[:24],
                'name': p.name,
                'path': str(p),
                'size_bytes': p.stat().st_size,
            }
            for p in sorted(paths) if str(p) not in known
        ]

    @app.get('/api/workspace/setup')
    def workspace_setup():
        return {'enabled':setup_enabled, 'initialized':workspace_initialized,
                'bundle_available':bool(bundled_dir and (bundled_dir/'seed.json').is_file()),
                'media_count':len(managed_media)}

    @app.post('/api/workspace/skip')
    def skip_setup():
        nonlocal workspace_initialized
        with state_lock:
            workspace_initialized = True
            persist_state()
        return {'initialized':True}

    @app.post('/api/workspace/import-defaults')
    def import_defaults():
        nonlocal workspace_initialized
        if not bundled_dir:
            raise HTTPException(404, '未安装默认素材包，可先导入自己的本地视频')
        from .showcase import load_bundle
        try:
            seed, catalog = load_bundle(bundled_dir)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(422, '默认素材包不完整，请检查文件后重试；现有记录不会被覆盖') from exc
        with state_lock:
            counts = {}
            # Merge by stable ID; never replace user edits, labels or disabled status.
            for name, current, incoming, key in (
                ('objects',library_items,seed['library_items'],'item_id'),
                ('tasks',review_tasks,seed['review_tasks'],'task_id'),
                ('media',managed_media,catalog,'media_id')):
                known = {item.get(key) for item in current}
                additions = [item for item in incoming if item.get(key) not in known]
                current.extend(deepcopy(additions))
                counts[name] = len(additions)
            workspace_initialized = True
            persist_state()
        return {'added':counts, 'initialized':True}

    @app.post('/api/media/import', status_code=201)
    def import_media(file: UploadFile = File(...)):
        """Copy a selected video into managed local storage, deduplicated by content."""
        nonlocal workspace_initialized
        import hashlib
        import math
        import tempfile
        import cv2
        if artifact_dir is None:
            raise HTTPException(503, '未配置本地素材存储')
        filename = Path(file.filename or '').name
        if Path(filename).suffix.lower() != '.mp4':
            raise HTTPException(422, '当前导入支持 MP4 视频，建议使用 H.264 编码')
        folder = artifact_dir/'media'
        folder.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest, size = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(suffix='.mp4', dir=folder, delete=False) as output:
                temporary = Path(output.name)
                while chunk := file.file.read(1024*1024):
                    size += len(chunk)
                    if size > 20*1024**3:
                        raise HTTPException(413, '单个视频不能超过 20 GB')
                    digest.update(chunk)
                    output.write(chunk)
            capture = cv2.VideoCapture(str(temporary))
            try:
                fps = capture.get(cv2.CAP_PROP_FPS)
                duration = capture.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps > 0 else 0
                ok, _ = capture.read()
            finally:
                capture.release()
            if not ok or not math.isfinite(duration) or duration <= 0:
                raise HTTPException(422, '视频无法读取，请确认文件完整且包含有效画面')
            media_id = digest.hexdigest()
            target = folder/(media_id+'.mp4')
            with state_lock:
                existing = next((m for m in managed_media if m.get('sha256')==media_id), None)
                if existing:
                    return {'duplicate':True, 'media':deepcopy(existing)}
                temporary.replace(target)
                media = {'media_id':media_id, 'sha256':media_id, 'name':filename,
                         'path':str(target.resolve()), 'url':f'/artifacts/media/{target.name}',
                         'size_bytes':size, 'duration_seconds':round(duration, 3),
                         'selection_note':'本地导入 · 尚未检查，请选择人物创建任务'}
                managed_media.append(media)
                workspace_initialized = True
                persist_state()
            return {'duplicate':False, 'media':media}
        except OSError as exc:
            raise HTTPException(503, '素材保存失败，请检查可用磁盘空间和目录权限') from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            file.file.close()

    @app.get("/api/library-items")
    def get_library_items(
        category: Literal["person", "text", "content"] | None = Query(default=None),
    ) -> list[dict[str, object]]:
        if category is None:
            return deepcopy(library_items)
        return [deepcopy(item) for item in library_items if item["category"] == category]

    @app.post("/api/library-items", status_code=status.HTTP_201_CREATED)
    def create_library_item(request: LibraryItemCreate) -> dict[str, object]:
        if not request.name.strip() or not request.classification.strip():
            raise HTTPException(422, '请填写对象名称和分类')
        if request.status != 'draft' or request.materials:
            raise HTTPException(422, '新建对象默认为草稿；参考素材和启用状态需通过后续流程维护')
        with state_lock:
            if any(item["item_id"] == request.item_id for item in library_items):
                raise HTTPException(status_code=409, detail="item_id already exists")
            item = request.model_dump()
            item.update(status='draft', materials=[], validation={'status':'not_started', 'note':'', 'decided_at':None}, lifecycle_history=[])
            append_lifecycle(item, 'created')
            library_items.append(item)
            persist_state()
        return deepcopy(item)

    @app.get("/api/library-items/{item_id}/materials")
    def get_library_item_materials(item_id: str) -> list[dict[str, object]]:
        item = next((item for item in library_items if item["item_id"] == item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="library item not found")
        return item["materials"]

    @app.put('/api/library-items/{item_id}')
    def edit_library_item(item_id: str, request: LibraryItemCreate):
        if not request.name.strip() or not request.classification.strip():
            raise HTTPException(422, '请填写对象名称和分类')
        with state_lock:
            item = next((i for i in library_items if i['item_id'] == item_id), None)
            if item is None:
                raise HTTPException(404, '对象不存在')
            if request.item_id != item_id or request.category != item['category']:
                raise HTTPException(422, '对象ID和类型不能修改')
            if request.status != item.get('status'):
                raise HTTPException(409, '对象启用状态只能通过状态流转操作修改')
            values = request.model_dump(exclude={'materials', 'status'})
            item.update(values)
            append_lifecycle(item, 'metadata_updated')
            persist_state()
            return deepcopy(item)

    @app.post('/api/library-items/{item_id}/validation')
    def record_library_validation(item_id: str, request: LibraryValidationDecision):
        with state_lock:
            item = next((i for i in library_items if i['item_id'] == item_id), None)
            if item is None:
                raise HTTPException(404, '对象不存在')
            if item.get('category') != 'person':
                raise HTTPException(409, '文字和内容能力尚未接入，不能记录为生产可用')
            if item.get('status') != 'ready_for_validation':
                raise HTTPException(409, '请先补齐参考照片并提交验证')
            if usable_reference_count(item) < 2:
                raise HTTPException(422, '至少需要两张可用参考照片，才能记录验证结论')
            validation = object_validation(item)
            validation.update(status=request.decision, note=request.note, decided_at=now_iso())
            if request.decision == 'failed':
                item['status'] = 'ready_for_material'
            append_lifecycle(item, f"validation_{request.decision}", request.note)
            persist_state()
            return deepcopy(item)

    @app.post('/api/library-items/{item_id}/lifecycle')
    def transition_library_item(item_id: str, request: LibraryLifecycleRequest):
        with state_lock:
            item = next((i for i in library_items if i['item_id'] == item_id), None)
            if item is None:
                raise HTTPException(404, '对象不存在')
            category = item.get('category')
            action = request.action
            if action in ('submit_for_validation', 'activate') and category != 'person':
                raise HTTPException(409, '当前仅人物画面检查已接入；该规则不能启用到生产审核')
            if action == 'submit_for_validation':
                if item.get('status') == 'active':
                    raise HTTPException(409, '对象已启用；变更参考素材后会自动回到待验证状态')
                if usable_reference_count(item) < 2:
                    raise HTTPException(422, '至少需要两张可用参考照片，才能提交验证')
                item['status'] = 'ready_for_validation'
                object_validation(item).update(status='pending', note='', decided_at=None)
            elif action == 'activate':
                if item.get('status') != 'ready_for_validation' or object_validation(item).get('status') != 'passed':
                    raise HTTPException(409, '请先完成并通过算法验证，再启用到生产审核')
                item['status'] = 'active'
            elif action == 'disable':
                item['status'] = 'disabled'
            elif action == 'restore':
                if category == 'person':
                    item['status'] = 'ready_for_validation' if usable_reference_count(item) >= 2 else 'ready_for_material'
                    object_validation(item).update(status='not_started', note='', decided_at=None)
                else:
                    item['status'] = 'draft'
            append_lifecycle(item, action, request.note)
            persist_state()
            return deepcopy(item)

    @app.post('/api/library-items/{item_id}/upload-reference', status_code=201)
    def upload_reference(item_id: str, file: UploadFile = File(...)):
        import hashlib
        import cv2
        import numpy as np
        if artifact_dir is None:
            raise HTTPException(503, '素材存储未配置')
        item = next((i for i in library_items if i['item_id'] == item_id and i['category'] == 'person'), None)
        if item is None:
            raise HTTPException(404, '人物对象不存在')
        content = file.file.read(15*1024*1024+1)
        if len(content) > 15*1024*1024:
            raise HTTPException(413, '图片不能超过15MB')
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(422, '无法解码图片，请使用JPEG或PNG')
        h,w = image.shape[:2]
        if max(h,w)>12000 or min(h,w)<32:
            raise HTTPException(422, '图片尺寸不适合参考图')
        if analyzer is not None and hasattr(analyzer, '_analysis_lock'):
            if not analyzer._analysis_lock.acquire(blocking=False):
                raise HTTPException(409, '分析器正在运行，请稍后导入图片')
            try:
                from .reference_quality import assess_reference
                quality=assess_reference(image,analyzer._detect_faces(image))
            finally:
                analyzer._analysis_lock.release()
            if quality['issues']:
                raise HTTPException(422, '；'.join(quality['issues'])+'。自动筛查仅作初筛，不代表身份确认。')
        digest = hashlib.sha256(content).hexdigest()
        folder = artifact_dir/'references'
        folder.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode('.jpg', image)
        if not ok:
            raise HTTPException(422, '图片转换失败')
        with state_lock:
            material_id = 'ref.'+digest
            if any(m['material_id'] == material_id for m in item['materials']):
                raise HTTPException(409, '此图片已存在')
            encoded.tofile(folder/f'{digest}.jpg')
            material = {'material_id':material_id, 'kind':'reference_image','title':Path(file.filename or '参考图').name, 'local_uri':f'/artifacts/references/{digest}.jpg', 'quality_note':f'{w}×{h}；本地参考图，身份及跨片效果待人工验证。','status':'pending_validation'}
            item['materials'].append(material)
            invalidate_object_validation(item, '参考照片已变更，需要重新确认验证结论')
            if item.get('status') == 'draft':
                item['status'] = 'ready_for_material'
            append_lifecycle(item, 'reference_imported', material['title'])
            persist_state()
            return material

    @app.post(
        "/api/library-items/{item_id}/materials",
        status_code=status.HTTP_201_CREATED,
    )
    def add_library_item_material(
        item_id: str, request: LibraryMaterial
    ) -> dict[str, object]:
        """Append a local reference asset without replacing the object library entry."""
        with state_lock:
            item = next((item for item in library_items if item["item_id"] == item_id), None)
            if item is None:
                raise HTTPException(status_code=404, detail="library item not found")
            materials = item.setdefault("materials", [])
            if any(material["material_id"] == request.material_id for material in materials):
                raise HTTPException(status_code=409, detail="material_id already exists")
            material = request.model_dump()
            materials.append(material)
            if item.get('category') == 'person' and material.get('kind') == 'reference_image':
                invalidate_object_validation(item, '参考照片已变更，需要重新确认验证结论')
                if item.get('status') == 'draft':
                    item['status'] = 'ready_for_material'
                append_lifecycle(item, 'reference_imported', material['title'])
            persist_state()
        return material

    @app.patch('/api/library-items/{item_id}/materials/{material_id}')
    def update_material_status(item_id: str, material_id: str, request: MaterialStatusUpdate):
        with state_lock:
            item=next((i for i in library_items if i['item_id']==item_id),None)
            material=next((m for m in (item or {}).get('materials',[]) if m['material_id']==material_id),None)
            if material is None:
                raise HTTPException(404,'参考照片不存在')
            material.update(request.model_dump())
            invalidate_object_validation(item, '参考照片状态已变更，需要重新确认验证结论')
            append_lifecycle(item, 'reference_updated', material.get('title', ''))
            persist_state()
            return deepcopy(material)

    @app.get("/api/review-tasks")
    def get_review_tasks(purpose: WorkspacePurpose | None = Query(default=None)) -> list[dict[str, object]]:
        tasks = review_tasks if purpose is None else [task for task in review_tasks if task.get('purpose', 'validation') == purpose]
        return [present_task(task) for task in tasks]

    @app.post("/api/review-tasks", status_code=status.HTTP_201_CREATED)
    def create_review_task(request: ReviewTaskCreate) -> dict[str, object]:
        validate_scope(request)
        if not request.asset_path.is_file():
            raise HTTPException(status_code=422, detail="asset_path does not exist")
        missing_objects = [
            item_id for item_id in request.object_ids
            if not any(item["item_id"] == item_id for item in library_items)
        ]
        if missing_objects:
            raise HTTPException(status_code=422, detail=f"unknown object ids: {', '.join(missing_objects)}")
        task = {
            "task_id": uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "name": request.name,
            "asset_path": str(request.asset_path),
            "object_ids": request.object_ids,
            "purpose": request.purpose,
            "capabilities": request.capabilities,
            "analysis_profile": CURRENT_ANALYSIS_PROFILE,
            "status": "ready",
            "channels": {"face": "available", "ocr": "not_configured", "asr": "not_configured", "content": "not_configured"},
        }
        with state_lock:
            review_tasks.insert(0, task)
            persist_state()
        return task

    @app.patch("/api/review-tasks/{task_id}")
    def update_review_task(task_id: str, request: ReviewTaskStatusUpdate) -> dict[str, object]:
        with state_lock:
            task = next((item for item in review_tasks if item["task_id"] == task_id), None)
            if task is None:
                raise HTTPException(status_code=404, detail="review task not found")
            if task.get('result') or task['status'] == 'running' or request.status not in ('draft', 'ready'):
                raise HTTPException(409, '执行与复核状态由实际操作更新')
            task["status"] = request.status
            persist_state()
        return task

    @app.patch("/api/review-tasks/{task_id}/name")
    def rename_review_task(task_id: str, request: ReviewTaskRename) -> dict[str, object]:
        with state_lock:
            task = next((item for item in review_tasks if item["task_id"] == task_id), None)
            if task is None:
                raise HTTPException(status_code=404, detail="review task not found")
            task["name"] = request.name.strip()
            persist_state()
            return present_task(task)

    @app.put('/api/review-tasks/{task_id}/scope')
    def edit_task_scope(task_id: str, request: ReviewTaskCreate):
        with state_lock:
            validate_scope(request)
            task = find_task(task_id)
            if task.get('result') or task['status'] == 'running':
                raise HTTPException(409, '已开始的任务不能修改审核范围')
            if not request.asset_path.is_file() or any(not any(i['item_id']==key for i in library_items) for key in request.object_ids):
                raise HTTPException(422, '媒资或审核对象不存在')
            task.update(name=request.name, asset_path=str(request.asset_path), object_ids=request.object_ids, purpose=request.purpose, capabilities=request.capabilities, analysis_profile=CURRENT_ANALYSIS_PROFILE)
            persist_state()
            return present_task(task)

    @app.post('/api/review-tasks/{task_id}/retry', status_code=201)
    def retry_task(task_id: str):
        with state_lock:
            source = deepcopy(find_task(task_id))
        if source['status'] == 'running':
            raise HTTPException(409, '请等待当前检查结束')
        request = ReviewTaskCreate(**{**source, 'name': source['name'] + ' · 重新检查'})
        created = create_review_task(request)
        with state_lock:
            created['previous_task_id'] = task_id
            persist_state()
        return deepcopy(created)

    @app.get("/api/overview")
    def get_overview(purpose: WorkspacePurpose | None = Query(default=None)) -> dict[str, object]:
        counts = {
            category: sum(item["category"] == category for item in library_items)
            for category in ("person", "text", "content")
        }
        workspace_tasks = review_tasks if purpose is None else [task for task in review_tasks if task.get('purpose', 'validation') == purpose]
        return {
            "workspace": purpose,
            "task_count": len(workspace_tasks),
            "task_statuses": {
                task_status: sum(task["status"] == task_status for task in workspace_tasks)
                for task_status in ("draft", "ready", "running", "needs_review", "completed", "failed")
            },
            "library_counts": counts,
            "tasks": [present_task(task) for task in workspace_tasks],
        }

    @app.get("/demo/{media_kind}")
    def get_demo_media(media_kind: str) -> FileResponse:
        media_path = (demo_media or {}).get(media_kind)
        if media_path is None or not media_path.is_file():
            raise HTTPException(status_code=404, detail="demo media not found")
        return FileResponse(media_path)

    @app.post("/api/jobs/{job_id}/run", status_code=status.HTTP_202_ACCEPTED)
    def run_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        request = job_inputs.get(job_id)
        if job is None or request is None:
            raise HTTPException(status_code=404, detail="job not found")
        if analyzer is None:
            raise HTTPException(status_code=503, detail="analyzer is not configured")

        job["status"] = "running"

        def on_progress(value: float) -> None:
            job["progress"] = max(0.0, min(1.0, value))

        try:
            job["events"] = analyzer.analyze(
                request.video_path,
                request.reference_image_path,
                request.person_name,
                on_progress,
            )
            job["progress"] = 1.0
            job["status"] = "completed"
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
        return job

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/artifacts", StaticFiles(directory=artifact_dir), name="artifacts")
    if bundled_dir is not None:
        app.mount('/bundled', StaticFiles(directory=bundled_dir), name='bundled')
    if frontend_dir is not None and frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app
