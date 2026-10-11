"""本地开发入口。

用法：
    python run.py                 # 默认 127.0.0.1:5000
    PORT=5059 python run.py       # 指定端口（PowerShell: $env:PORT=5059）

注意：开发服务器仅用于本地调试，生产环境请使用 Gunicorn（见 Dockerfile）。
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug, threaded=True)

