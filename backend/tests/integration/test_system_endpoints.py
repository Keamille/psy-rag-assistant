"""系统接口的集成测试（开发文档 7.8）。"""

from __future__ import annotations


def test_health(client):
    body = client.get("/api/v1/health").get_json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["service"] == "psy-rag-assistant"


def test_ready_reports_each_dependency(client):
    resp = client.get("/api/v1/ready")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert set(data) == {"database", "redis", "chroma", "embedding", "llm"}
    assert data["database"]["status"] == "ok"
    # 本机未接 Redis / Chroma / torch，应以 degraded 呈现而不是让接口失败
    assert data["redis"]["status"] in {"ok", "degraded"}
    assert data["chroma"]["status"] in {"ok", "degraded"}
    assert data["embedding"]["status"] in {"ok", "degraded"}
    assert data["llm"]["status"] in {"ok", "configured", "unconfigured", "degraded"}


def test_ready_deep_mode_does_not_crash_without_api_key(client):
    resp = client.get("/api/v1/ready?deep=1")
    assert resp.status_code == 200


def test_meta_hotlines_returns_real_data(client):
    body = client.get("/api/v1/meta/hotlines").get_json()
    phones = {item["phone"] for item in body["data"]["items"]}
    assert "12356" in phones
    assert body["data"]["verified_at"]


def test_meta_hotlines_unknown_region(client):
    resp = client.get("/api/v1/meta/hotlines?region=XX")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == 1001


def test_meta_config_exposes_disclaimer(client):
    body = client.get("/api/v1/meta/config").get_json()
    data = body["data"]
    assert data["disclaimer_version"]
    assert "不能替代专业诊断" in data["disclaimer_markdown"]
    assert data["max_message_length"] == 4000
    assert data["features"]["scale_assessment"] is False


def test_meta_build_reports_version_and_features(client):
    """服务信息只报版本与能力开关，不再有阶段/待交付之类会误导用户的字段。"""
    data = client.get("/api/v1/meta/build").get_json()["data"]
    assert data["name"] == "psy-rag-assistant"
    assert data["version"]
    assert data["features"]["rag"] is True
    assert data["features"]["crisis_intervention"] is True
    # 不允许再出现阶段或待交付的字样
    text = client.get("/api/v1/meta/build").get_data(as_text=True)
    for word in ("M0", "M1", "M2", "M3", "待交付", "尚未"):
        assert word not in text, f"服务信息里仍出现 {word}"

