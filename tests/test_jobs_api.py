from pathlib import Path
from time import monotonic, sleep

from fastapi.testclient import TestClient

from face_watch.api import create_app


class ExampleAnalyzer:
    def analyze(self, video_path, reference_image_path, person_name, on_progress):
        on_progress(0.5)
        return [
            {
                "person_name": person_name,
                "start_seconds": 12.4,
                "end_seconds": 18.8,
                "best_score": 0.72,
                "decision": "confirmed",
                "evidence_image": "/evidence/job/frame.jpg",
            }
        ]


def test_user_can_create_a_video_face_search_job(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")

    client = TestClient(create_app())
    response = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "测试人物",
            "run_async": False,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": response.json()["job_id"],
        "status": "queued",
        "person_name": "测试人物",
    }


def test_user_can_read_job_status_and_empty_results(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app())

    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "测试人物",
            "run_async": False,
        },
    ).json()

    response = client.get(f"/api/jobs/{created['job_id']}")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": created["job_id"],
        "status": "queued",
        "person_name": "测试人物",
        "progress": 0.0,
        "events": [],
        "error": None,
    }


def test_user_can_run_job_and_read_match_events(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app(analyzer=ExampleAnalyzer()))
    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "许灵均",
            "run_async": False,
        },
    ).json()

    run_response = client.post(f"/api/jobs/{created['job_id']}/run")
    result = client.get(f"/api/jobs/{created['job_id']}").json()

    assert run_response.status_code == 202
    assert result["status"] == "completed"
    assert result["progress"] == 1.0
    assert result["events"] == [
        {
            "person_name": "许灵均",
            "start_seconds": 12.4,
            "end_seconds": 18.8,
            "best_score": 0.72,
            "decision": "confirmed",
            "evidence_image": "/evidence/job/frame.jpg",
        }
    ]


def test_async_job_completes_without_blocking_creation(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app(analyzer=ExampleAnalyzer()))

    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "许灵均",
            "run_async": True,
        },
    )

    assert created.status_code == 202
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        result = client.get(f"/api/jobs/{created.json()['job_id']}").json()
        if result["status"] == "completed":
            break
        sleep(0.01)
    assert result["status"] == "completed"


def test_web_ui_and_evidence_are_served(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    artifacts = tmp_path / "artifacts"
    frontend.mkdir()
    artifacts.mkdir()
    (frontend / "ui-assets").mkdir()
    (frontend / "index.html").write_text("<main>Face Watch</main>", encoding="utf-8")
    (frontend / "ui-assets" / "app-hash.js").write_text("export {}", encoding="utf-8")
    (artifacts / "evidence.jpg").write_bytes(b"evidence")
    client = TestClient(
        create_app(frontend_dir=frontend, artifact_dir=artifacts)
    )

    page = client.get("/")
    application_asset = client.get("/ui-assets/app-hash.js")
    evidence = client.get("/artifacts/evidence.jpg")

    assert page.status_code == 200
    assert "Face Watch" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert application_asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert evidence.status_code == 200
    assert evidence.content == b"evidence"


def test_web_ui_can_load_demo_defaults() -> None:
    client = TestClient(
        create_app(
            defaults={
                "video_path": "/demo/movie.mp4",
                "reference_image_path": "/demo/person.png",
                "person_name": "许灵均",
            }
        )
    )

    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "video_path": "/demo/movie.mp4",
        "reference_image_path": "/demo/person.png",
        "person_name": "许灵均",
    }


def test_prototype_exposes_governed_library_and_real_task_overview(tmp_path: Path) -> None:
    client = TestClient(create_app())
    asset = tmp_path / "movie.mp4"
    asset.write_bytes(b"video")

    library = client.get("/api/library-items")
    created = client.post(
        "/api/review-tasks",
        json={
            "name": "样片审核",
            "asset_path": str(asset),
            "object_ids": ["person.zhao_benshan"],
        },
    )
    overview = client.get("/api/overview")

    assert library.status_code == 200
    assert any(item["item_id"] == "person.zhao_benshan" for item in library.json())
    assert created.status_code == 201
    assert created.json()["status"] == "ready"
    assert overview.status_code == 200
    assert overview.json()["task_count"] == 1
    assert overview.json()["tasks"][0]["name"] == "样片审核"
    people = client.get("/api/library-items?category=person")
    assert people.status_code == 200
    assert all(item["category"] == "person" for item in people.json())


def test_user_can_add_a_library_item_without_overwriting_existing_one() -> None:
    client = TestClient(create_app())
    payload = {
        "item_id": "person.example_actor",
        "category": "person",
        "name": "示例演员",
        "aliases": ["示例别名"],
        "definition": "待接入授权参考图与独立测试媒资。",
        "status": "draft",
    }

    created = client.post("/api/library-items", json=payload)
    duplicate = client.post("/api/library-items", json=payload)

    assert created.status_code == 201
    assert created.json()["item_id"] == payload["item_id"]
    assert created.json()["status"] == "draft"
    assert created.json()["materials"] == []
    assert created.json()["validation"]["status"] == "not_started"
    assert created.json()["lifecycle_history"][-1]["event"] == "created"
    assert duplicate.status_code == 409


def test_person_library_item_exposes_attributable_reference_materials() -> None:
    client = TestClient(create_app())

    response = client.get("/api/library-items/person.jackie_chan/materials")

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert response.json()[0]["material_id"] == "ref.jackie_chan.locarno_2025"
    assert response.json()[0]["status"] == "pending_validation"


def test_user_can_append_a_second_reference_to_a_library_object() -> None:
    client = TestClient(create_app())
    material = {
        "material_id": "ref.jackie_chan.validation_2",
        "kind": "reference_image",
        "title": "成龙补充参考图",
        "local_uri": "/assets/references/jackie-chan-validation-2.jpg",
        "quality_note": "本地单脸候选参考图。",
        "status": "pending_validation",
    }

    created = client.post(
        "/api/library-items/person.jackie_chan/materials", json=material
    )
    duplicate = client.post(
        "/api/library-items/person.jackie_chan/materials", json=material
    )
    materials = client.get("/api/library-items/person.jackie_chan/materials")

    assert created.status_code == 201
    assert created.json() == material
    assert duplicate.status_code == 409
    assert [item["material_id"] for item in materials.json()] == [
        "ref.jackie_chan.locarno_2025",
        "ref.jackie_chan.2007",
        "ref.jackie_chan.2016",
        "ref.jackie_chan.validation_2",
    ]


def test_zhu_shimao_local_demo_material_is_available_for_validation(tmp_path: Path) -> None:
    reference = tmp_path / "zhu-shimao.jpeg"
    reference.write_bytes(b"reference")
    client = TestClient(create_app(demo_media={"reference": reference}))

    response = client.get("/api/library-items/person.zhu_shimao/materials")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[:1] == [
        {
            "material_id": "ref.zhu_shimao.local_demo",
            "kind": "reference_image",
            "title": "朱时茂正面参考照（本地 Demo）",
            "local_uri": "/demo/reference",
            "quality_note": "447×447；单人正面清晰照，作为《牧马人》本地 Demo 的检索参考输入。",
            "status": "pending_validation",
        }
    ]


def test_gong_li_has_multiple_local_front_reference_images() -> None:
    client = TestClient(create_app())

    response = client.get("/api/library-items/person.gong_li/materials")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert all(material["local_uri"] for material in response.json())
    assert response.json()[-1]["title"] == "巩俐戛纳近景（2011，视角二）"


def test_web_ui_can_preview_configured_demo_media(tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video-bytes")
    reference.write_bytes(b"image-bytes")
    client = TestClient(
        create_app(
            demo_media={"video": video, "reference": reference}
        )
    )

    video_response = client.get("/demo/video")
    reference_response = client.get("/demo/reference")

    assert video_response.status_code == 200
    assert video_response.content == b"video-bytes"
    assert reference_response.status_code == 200
    assert reference_response.content == b"image-bytes"
