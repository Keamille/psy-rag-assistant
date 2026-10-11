"""命令行入口。

docker-compose 的 web 启动链会依次执行：
    alembic upgrade head
    python -m app.cli init-admin
    python -m app.cli seed-knowledge

所以这两条命令必须**幂等且不因"已存在"而失败**——
容器每次重启都会跑一遍，失败会导致反复重启。
"""

from __future__ import annotations

import sys

import click

from app import create_app
from app.core.clock import utcnow
from app.core.security import ROLE_ADMIN, hash_password
from app.extensions import db
from app.models import User

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "ChangeMe12345"


@click.group()
def cli() -> None:
    """心理咨询 AI 助手 管理命令。"""


@cli.command("init-admin")
@click.option("--username", default=DEFAULT_ADMIN_USERNAME, help="管理员用户名")
@click.option("--email", default=DEFAULT_ADMIN_EMAIL, help="管理员邮箱")
@click.option(
    "--password",
    default=None,
    help=f"管理员密码，缺省用 {DEFAULT_ADMIN_PASSWORD}（首次登录后请立即修改）",
)
def init_admin(username: str, email: str, password: str | None) -> None:
    """创建初始管理员账号。已存在则跳过，不报错。"""
    app = create_app()
    with app.app_context():
        existing = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing is not None:
            # 已经存在时只确保角色正确，不重置密码——否则每次重启
            # 都会把管理员改过的密码冲掉，这是个很容易埋下的坑。
            if existing.role != ROLE_ADMIN:
                existing.role = ROLE_ADMIN
                db.session.commit()
                click.echo(f"[ok] 已把 {existing.username} 提升为管理员")
            else:
                click.echo(f"[skip] 管理员 {existing.username} 已存在，未做改动")
            return

        initial_password = password or DEFAULT_ADMIN_PASSWORD
        admin = User(
            username=username,
            email=email,
            password_hash=hash_password(initial_password),
            role=ROLE_ADMIN,
            status="active",
            consent_version=app.config["CONSENT_VERSION"],
            consented_at=utcnow(),
        )
        db.session.add(admin)
        db.session.commit()

        click.echo(f"[ok] 已创建管理员 {username}（邮箱 {email}）")
        if password is None:
            click.echo(
                f"[!] 当前密码是默认值 {DEFAULT_ADMIN_PASSWORD}，"
                "请立即登录后在「设置」里修改"
            )


@cli.command("seed-knowledge")
def seed_knowledge() -> None:
    """把内置基础语料入库。幂等：已入库的文件会跳过。"""
    app = create_app()
    with app.app_context():
        from app.services.document_service import seed_base_knowledge

        try:
            result = seed_base_knowledge()
        except Exception as exc:  # noqa: BLE001
            # 内置语料入库失败不该阻止容器启动：模型可能还没下载完、
            # Chroma 可能还没起来。此时让 web 正常提供服务，
            # 由管理员稍后在后台手动重建即可。
            click.echo(f"[warn] 内置语料入库失败（不影响服务启动）：{exc}")
            return

        click.echo(
            f"[ok] 内置语料：新入库 {result['seeded']} 篇，跳过 {result['skipped']} 篇"
        )


@cli.command("routes")
def list_routes() -> None:
    """打印全部已注册路由，用于自检。"""
    app = create_app()
    rules = sorted(
        (str(rule), ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"})))
        for rule in app.url_map.iter_rules()
    )
    for path, methods in rules:
        click.echo(f"{methods:20s} {path}")
    click.echo(f"共 {len(rules)} 条路由")


def main() -> int:
    cli()
    return 0


if __name__ == "__main__":
    sys.exit(main())

