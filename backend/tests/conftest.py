"""pytest 公共夹具。

注意：`core/security.load_current_user` 会回查数据库做二次校验，
因此凡是访问受保护接口的测试，都必须先建出真实用户——
"凭空造一个令牌"已经不够了。
"""

from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.core.clock import utcnow
from app.core.security import hash_password
from app.extensions import db
from app.models import User

DEFAULT_PASSWORD = "Str0ngP@ssw0rd"


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def stub_embedder(monkeypatch):
    """把向量化替换成确定性假实现。

    真实的 bge-m3 有 2.3GB，加载要十几秒；测试里既不该花这个时间，
    也不该让测试依赖模型文件是否存在。假向量按文本哈希生成，
    同一个输入永远得到同一个向量，检索排序在测试里是可复现的。
    """
    import hashlib

    import app.rag.embedder as embedder

    def _fake_vector(text: str, dim: int = 1024) -> list[float]:
        seed = hashlib.sha256((text or "").encode("utf-8")).digest()
        # 用摘要反复扩展成 dim 维，再做 L2 归一化，模拟真实向量的性质
        raw = [(seed[i % len(seed)] / 255.0) - 0.5 for i in range(dim)]
        norm = sum(value * value for value in raw) ** 0.5 or 1.0
        return [value / norm for value in raw]

    monkeypatch.setattr(embedder, "embed_query", _fake_vector)
    monkeypatch.setattr(embedder, "embed_documents", lambda texts: [_fake_vector(t) for t in texts])
    monkeypatch.setattr(embedder, "is_loaded", lambda: True)
    monkeypatch.setattr(embedder, "warmup", lambda: None)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def url_map(app):
    """返回 {路径: 方法集合} 便于断言路由注册情况。"""
    result: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        methods = set(rule.methods or set()) - {"HEAD", "OPTIONS"}
        result.setdefault(str(rule), set()).update(methods)
    return result


@pytest.fixture()
def make_user(app):
    """创建一个真实用户并返回它。"""
    counter = {"n": 0}

    def _make(
        role: str = "user",
        status: str = "active",
        password: str = DEFAULT_PASSWORD,
        username: str | None = None,
        email: str | None = None,
    ) -> User:
        counter["n"] += 1
        suffix = counter["n"]
        user = User(
            username=username or f"tester{suffix}",
            email=email or f"tester{suffix}@example.com",
            password_hash=hash_password(password),
            role=role,
            status=status,
            consent_version="v1.0",
            consented_at=utcnow(),
        )
        db.session.add(user)
        db.session.commit()
        return user

    return _make


@pytest.fixture()
def auth_headers(make_user):
    """造一个已登录用户的请求头。

    返回 (headers, user) 二元组，便于测试里拿 user.id 做断言。
    """

    def _make(role: str = "user", status: str = "active"):
        user = make_user(role=role, status=status)
        token = create_access_token(
            identity=str(user.id), additional_claims={"role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}, user

    return _make


@pytest.fixture()
def refresh_headers(make_user):
    """造一个持有 refresh 令牌的已登录用户。"""
    from flask_jwt_extended import create_refresh_token

    def _make(role: str = "user", status: str = "active"):
        user = make_user(role=role, status=status)
        token = create_refresh_token(identity=str(user.id))
        return {"Authorization": f"Bearer {token}"}, user

    return _make

