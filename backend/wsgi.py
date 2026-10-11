"""Gunicorn 入口。

容器内由 docker-compose 通过 `gunicorn ... wsgi:app` 启动。
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 便于本地直接 `python wsgi.py` 调试
    app.run(host="127.0.0.1", port=5000, debug=False)

