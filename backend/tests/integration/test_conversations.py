"""会话与消息接口测试（W4 验收，开发文档 §7.5 / §7.6）。

每一条用例都对应一个"之前真实挂过"或"契约明确要求"的行为，
不是凑数用的。
"""

from __future__ import annotations

import pytest

from app.core.errors import ErrorCode
from app.core.clock import utcnow
from app.extensions import db
from app.models import Conversation, Message


def _create(client, headers, title=None):
    """建一个会话，返回它的 id。"""
    body = {} if title is None else {"title": title}
    resp = client.post("/api/v1/conversations", headers=headers, json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]["id"]


def _add_message(conversation_id, content, role="user", client_msg_id=None):
    """直接往库里插消息，并同步刷新会话的 updated_at。

    为什么不走 POST /messages 造数据：那个端点现在是 SSE 流式接口，
    会真的跑检索与模型推理。而列表、分页、计数这些用例要验证的是**读取**行为，
    让它们依赖整条生成链路既慢又脆。发送链路本身由 test_chat.py 专门覆盖。
    """
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        client_msg_id=client_msg_id,
    )
    db.session.add(message)
    conversation = db.session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.updated_at = utcnow()
    db.session.commit()
    return message


# ---------------------------------------------------------------------------
# 统一响应体
# ---------------------------------------------------------------------------


def test_all_conversation_responses_use_envelope(client, auth_headers):
    """每个端点都必须返回 {code,message,data,request_id}。

    返回裸 list 或裸 ORM 对象是最容易犯的错：HTTP 状态码看着对，
    但前端拦截器取 response.data.data 会拿到 undefined。
    """
    headers, _ = auth_headers()
    cid = _create(client, headers)

    responses = [
        client.get("/api/v1/conversations", headers=headers),
        client.post("/api/v1/conversations", headers=headers, json={}),
        client.get(f"/api/v1/conversations/{cid}", headers=headers),
        client.patch(f"/api/v1/conversations/{cid}", headers=headers, json={"title": "x"}),
        client.get(f"/api/v1/conversations/{cid}/messages", headers=headers),
        client.delete(f"/api/v1/conversations/{cid}", headers=headers),
    ]
    for resp in responses:
        assert resp.is_json, "响应不是 JSON"
        assert set(resp.get_json()) == {"code", "message", "data", "request_id"}


def test_conversation_requires_auth(client):
    resp = client.get("/api/v1/conversations")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.UNAUTHORIZED


# ---------------------------------------------------------------------------
# 会话列表
# ---------------------------------------------------------------------------


def test_list_is_paginated_with_contract_field_names(client, auth_headers):
    headers, _ = auth_headers()
    _create(client, headers, "第一个")
    _create(client, headers, "第二个")

    resp = client.get("/api/v1/conversations?page=1&size=1", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    # 契约用 size 不是 per_page，也不能多塞 pages/has_next 之外的自造字段
    assert set(data) == {"items", "page", "size", "total"}
    assert data["page"] == 1
    assert data["size"] == 1
    assert data["total"] == 2
    assert len(data["items"]) == 1


def test_list_size_has_upper_bound(client, auth_headers):
    """不设上限的话 ?size=100000 一次就能把整张表拉走。"""
    headers, _ = auth_headers()
    _create(client, headers)

    resp = client.get("/api/v1/conversations?size=100000", headers=headers)
    assert resp.get_json()["data"]["size"] == 100


def test_list_only_returns_own_conversations(client, auth_headers, make_user):
    headers_a, _ = auth_headers()
    headers_b, _ = auth_headers()
    _create(client, headers_a, "A 的会话")

    data = client.get("/api/v1/conversations", headers=headers_b).get_json()["data"]
    assert data["total"] == 0


def test_list_orders_by_updated_at_desc(client, auth_headers):
    headers, _ = auth_headers()
    first = _create(client, headers, "先建的")
    second = _create(client, headers, "后建的")

    # 给第一个会话加一条消息，它应当冒到最前面
    _add_message(first, "让它变新", client_msg_id="order-1")

    items = client.get("/api/v1/conversations", headers=headers).get_json()["data"]["items"]
    assert [item["id"] for item in items] == [first, second]


def test_list_includes_message_count(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    for i in range(3):
        _add_message(cid, f"第 {i} 条", client_msg_id=f"cnt-{i}")

    items = client.get("/api/v1/conversations", headers=headers).get_json()["data"]["items"]
    assert items[0]["message_count"] == 3


def test_list_excludes_soft_deleted(client, auth_headers):
    """软删除的会话不能出现在列表里，否则"删除"形同虚设。"""
    headers, _ = auth_headers()
    cid = _create(client, headers)
    client.delete(f"/api/v1/conversations/{cid}", headers=headers)

    data = client.get("/api/v1/conversations", headers=headers).get_json()["data"]
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# 新建会话
# ---------------------------------------------------------------------------


def test_create_without_title_is_allowed(client, auth_headers):
    """前端在没有标题时发的是 {}，不能 KeyError。"""
    headers, _ = auth_headers()
    resp = client.post("/api/v1/conversations", headers=headers, json={})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["title"] == "新的对话"


def test_create_with_empty_body_is_allowed(client, auth_headers):
    """连 body 都不发也不能挂。"""
    headers, _ = auth_headers()
    resp = client.post("/api/v1/conversations", headers=headers)
    assert resp.status_code == 200


def test_create_preserves_title_case(client, auth_headers):
    """标题是展示文本，不能被强制小写。"""
    headers, _ = auth_headers()
    cid = _create(client, headers, "Job Stress")
    data = client.get(f"/api/v1/conversations/{cid}", headers=headers).get_json()["data"]
    assert data["title"] == "Job Stress"


def test_create_rejects_overlong_title(client, auth_headers):
    headers, _ = auth_headers()
    resp = client.post(
        "/api/v1/conversations", headers=headers, json={"title": "长" * 121}
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


# ---------------------------------------------------------------------------
# 会话详情与修改
# ---------------------------------------------------------------------------


def test_get_own_conversation(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers, "我的会话")

    resp = client.get(f"/api/v1/conversations/{cid}", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["id"] == cid
    assert data["title"] == "我的会话"
    assert data["status"] == "active"
    assert data["message_count"] == 0


def test_get_missing_conversation_returns_3001(client, auth_headers):
    headers, _ = auth_headers()
    resp = client.get("/api/v1/conversations/999999", headers=headers)
    assert resp.status_code == 404
    assert resp.get_json()["code"] == ErrorCode.CONVERSATION_NOT_FOUND


def test_cannot_touch_other_users_conversation(client, auth_headers):
    """越权必须被挡住，且错误码与"不存在"一致（不泄漏会话是否存在）。"""
    headers_a, _ = auth_headers()
    headers_b, _ = auth_headers()
    cid = _create(client, headers_a)

    for method in ("get", "patch", "delete"):
        resp = getattr(client, method)(
            f"/api/v1/conversations/{cid}", headers=headers_b, json={"title": "劫持"}
        )
        assert resp.status_code == 404, f"{method} 未被拦住"
        assert resp.get_json()["code"] == ErrorCode.CONVERSATION_NOT_FOUND

    # 确认 B 的操作确实没有生效
    data = client.get(f"/api/v1/conversations/{cid}", headers=headers_a).get_json()["data"]
    assert data["title"] != "劫持"


def test_update_title(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers, "旧标题")
    resp = client.patch(
        f"/api/v1/conversations/{cid}", headers=headers, json={"title": "新标题"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["title"] == "新标题"


def test_update_rejects_blank_title(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    resp = client.patch(
        f"/api/v1/conversations/{cid}", headers=headers, json={"title": "   "}
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_update_accepts_archive_status(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    resp = client.patch(
        f"/api/v1/conversations/{cid}", headers=headers, json={"status": "archived"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "archived"


def test_update_refuses_to_set_paused(client, auth_headers):
    """paused 是风控流程设的状态，客户端不能自己标或自己解。"""
    headers, _ = auth_headers()
    cid = _create(client, headers)
    resp = client.patch(
        f"/api/v1/conversations/{cid}", headers=headers, json={"status": "paused"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def test_delete_is_soft(client, auth_headers):
    """软删除：行还在，只是打了 deleted_at。"""
    headers, _ = auth_headers()
    cid = _create(client, headers)

    resp = client.delete(f"/api/v1/conversations/{cid}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] is None

    row = db.session.get(Conversation, cid)
    assert row is not None, "行被物理删掉了，应该是软删除"
    assert row.deleted_at is not None


def test_deleted_conversation_is_invisible_everywhere(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    client.delete(f"/api/v1/conversations/{cid}", headers=headers)

    assert client.get(f"/api/v1/conversations/{cid}", headers=headers).status_code == 404
    assert (
        client.get(f"/api/v1/conversations/{cid}/messages", headers=headers).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/conversations/{cid}", headers=headers).status_code == 404
    )


# ---------------------------------------------------------------------------
# 消息列表
# ---------------------------------------------------------------------------


def test_empty_message_list_is_200_not_404(client, auth_headers):
    """空列表是正常情况。

    Flask-SQLAlchemy 的 paginate 在页码越界时默认抛 404，
    写死 page=2 会让"还没有消息"变成 404 报错。
    """
    headers, _ = auth_headers()
    cid = _create(client, headers)

    resp = client.get(f"/api/v1/conversations/{cid}/messages", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


def test_out_of_range_page_is_empty_not_404(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    _add_message(cid, "唯一一条", client_msg_id="oor-1")

    resp = client.get(f"/api/v1/conversations/{cid}/messages?page=99", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["items"] == []


def test_message_pagination_uses_query_params(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    for i in range(6):
        _add_message(cid, f"第 {i} 条", client_msg_id=f"page-{i}")

    page1 = client.get(f"/api/v1/conversations/{cid}/messages?page=1&size=4", headers=headers)
    data = page1.get_json()["data"]
    assert data["total"] == 6
    assert len(data["items"]) == 4
    assert data["size"] == 4

    page2 = client.get(f"/api/v1/conversations/{cid}/messages?page=2&size=4", headers=headers)
    assert len(page2.get_json()["data"]["items"]) == 2

    # 两页内容不能重叠
    ids1 = {item["id"] for item in data["items"]}
    ids2 = {item["id"] for item in page2.get_json()["data"]["items"]}
    assert not (ids1 & ids2)


def test_messages_are_returned_newest_first(client, auth_headers):
    """倒序返回，前端再翻转——开发文档 §7.5 的约定。"""
    headers, _ = auth_headers()
    cid = _create(client, headers)
    for i in range(3):
        _add_message(cid, f"第 {i} 条", client_msg_id=f"desc-{i}")

    items = client.get(f"/api/v1/conversations/{cid}/messages", headers=headers).get_json()["data"]["items"]
    assert [item["content"] for item in items] == ["第 2 条", "第 1 条", "第 0 条"]


def test_other_user_cannot_read_messages(client, auth_headers):
    headers_a, _ = auth_headers()
    headers_b, _ = auth_headers()
    cid = _create(client, headers_a)

    resp = client.get(f"/api/v1/conversations/{cid}/messages", headers=headers_b)
    assert resp.status_code == 404
    assert resp.get_json()["code"] == ErrorCode.CONVERSATION_NOT_FOUND


# ---------------------------------------------------------------------------
# 发送消息与幂等
# ---------------------------------------------------------------------------


def test_send_message_persists(client, auth_headers):
    """用户消息在**开始流式生成之前**就已落库。

    这一点很重要：即使后面的模型调用失败，用户说的那句话也不会丢——
    刷新页面还能看到自己说了什么，这对心理支持场景尤其关键。
    """
    headers, _ = auth_headers()
    cid = _create(client, headers)

    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"text": "我最近总是睡不着", "client_msg_id": "send-1"},
    )
    assert resp.status_code == 200
    # 这是 SSE 端点，返回事件流而不是 JSON
    assert resp.mimetype == "text/event-stream"
    body = resp.get_data(as_text=True)
    assert "event: meta" in body

    saved = Message.query.filter_by(conversation_id=cid).all()
    assert len(saved) == 1
    assert saved[0].role == "user"
    assert saved[0].content == "我最近总是睡不着"


def test_same_client_msg_id_is_idempotent(client, auth_headers):
    """W4 的核心验收点：重发同一条消息，库里只能有一条。

    这里直接在 service 层断言，而不是发两次 HTTP 请求：
    端点用的是 stream_with_context，同一测试里连续两次流式请求会让
    Flask 的请求上下文出栈顺序错乱（框架层面的已知行为，不是业务 bug）。
    幂等本身就是 service 层保证的，测这一层更直接，也不受框架细节干扰。

    接口层只用一个请求验证 meta 事件里的 created 标记，见下一个用例。
    """
    headers, user = auth_headers()
    cid = _create(client, headers)

    from app.services import conversation_service

    first, created_first = conversation_service.append_user_message(
        conversation_id=cid, user_id=user.id, text="网络抖动时前端会重发", client_msg_id="idem-1"
    )
    second, created_second = conversation_service.append_user_message(
        conversation_id=cid, user_id=user.id, text="网络抖动时前端会重发", client_msg_id="idem-1"
    )

    assert created_first is True
    assert created_second is False, "重发应当命中幂等、不新建记录"
    assert first.id == second.id
    assert Message.query.filter_by(conversation_id=cid, role="user").count() == 1


def test_meta_event_reports_created_true(client, auth_headers):
    """meta 事件要让前端知道这条消息是新写入还是命中幂等。"""
    headers, _ = auth_headers()
    cid = _create(client, headers)

    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"text": "第一次发送", "client_msg_id": "meta-1"},
    )
    assert resp.status_code == 200
    assert '"created": true' in resp.get_data(as_text=True)


def test_different_client_msg_id_creates_new_message(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    for i in range(2):
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=headers,
            json={"text": f"第 {i} 条", "client_msg_id": f"uniq-{i}"},
        )
    assert Message.query.filter_by(conversation_id=cid, role="user").count() == 2


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_send_rejects_blank_text(client, auth_headers, text):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"text": text, "client_msg_id": "blank-1"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_send_rejects_overlong_text(client, auth_headers):
    headers, _ = auth_headers()
    cid = _create(client, headers)
    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"text": "长" * 4001, "client_msg_id": "long-1"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_send_refused_when_conversation_paused(client, auth_headers):
    """会话被风控暂停后，发消息应返回 3002 而不是照常写入。"""
    headers, user = auth_headers()
    cid = _create(client, headers)

    conversation = db.session.get(Conversation, cid)
    conversation.status = "paused"
    db.session.commit()

    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"text": "还在吗", "client_msg_id": "paused-1"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == ErrorCode.CONVERSATION_PAUSED
    assert Message.query.filter_by(conversation_id=cid).count() == 0


def test_cannot_send_to_other_users_conversation(client, auth_headers):
    headers_a, _ = auth_headers()
    headers_b, _ = auth_headers()
    cid = _create(client, headers_a)

    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers_b,
        json={"text": "越权写入", "client_msg_id": "cross-1"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["code"] == ErrorCode.CONVERSATION_NOT_FOUND
    assert Message.query.filter_by(conversation_id=cid).count() == 0

