"""预下载 BGE 系列模型到本地，供容器或宿主机加载（开发文档 §13.5）。

为什么需要它：容器首次启动时才下载 4.6GB 权重，在内网环境常常失败，
而且会把 healthcheck 的 start_period 拖超时。先在本机下载好再挂载更稳。

用法：
    python backend/scripts/download_models.py --target ./models/hf-cache

三条约束：

1. **不能用 hf-mirror.com。** 镜像的 `resolve` 端点返回的是"裸 302"，
   缺少 `X-Repo-Commit` / `ETag` 等 huggingface_hub 用来构造元数据的响应头，
   会直接抛 `FileMetadataError: Distant resource does not seem to be on huggingface.co`。
   （curl 不校验这些头，所以能下 —— 容易误判成网络问题。）
   本脚本默认清掉 HF_ENDPOINT，强制走官方源。

2. **必须跳过 ONNX 文件。** bge-m3 仓库里有两个 2GB 级的权重：
   `pytorch_model.bin`（我们要的）和 `onnx/model.onnx_data`（ONNX 变体，用不到）。
   不跳过就白下 2.1GB。

3. **缓存要落在 HF_HOME/hub 下。** huggingface 的标准布局是
   `$HF_HOME/hub/models--组织--模型/`。如果直接下到 `$HF_HOME/`，
   运行时按模型名找不到文件，会报"看起来 BAAI/bge-m3 不是包含 config.json 的目录"。
"""

from __future__ import annotations

import argparse
import os
import sys
import time

DEFAULT_MODELS = ("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3")
DEFAULT_TARGET = "./models/hf-cache"

# ONNX 变体与训练用的额外权重，推理时不需要
IGNORE_PATTERNS = ["onnx/*", "*.onnx", "*.onnx_data"]


def main() -> int:
    parser = argparse.ArgumentParser(description="预下载 BGE 模型权重")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="HF_HOME 目录；模型会落在 <target>/hub/ 下",
    )
    parser.add_argument(
        "--use-mirror",
        action="store_true",
        help="使用 hf-mirror.com（默认不用；见文件头部第 1 条说明）",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("缺少依赖： pip install huggingface_hub", file=sys.stderr)
        return 1

    if args.use_mirror:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    else:
        # 显式清掉，避免从 .env 或系统环境里继承到镜像配置
        os.environ.pop("HF_ENDPOINT", None)

    # 2GB 文件的首次响应很容易超过默认的 10 秒
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

    target = os.path.abspath(args.target)
    cache_dir = os.path.join(target, "hub")  # 见文件头部第 3 条
    os.makedirs(cache_dir, exist_ok=True)

    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co（官方源）")
    print(f"下载源：{endpoint}")
    print(f"目标目录：{cache_dir}\n")

    failed = []
    for model in args.models:
        started = time.time()
        print(f"[下载中] {model} ...")
        try:
            path = snapshot_download(
                repo_id=model,
                cache_dir=cache_dir,
                max_workers=2,
                ignore_patterns=IGNORE_PATTERNS,
            )
            print(f"[完成]   {model}  用时 {time.time() - started:.0f}s\n  -> {path}\n")
        except Exception as exc:  # noqa: BLE001
            failed.append((model, exc))
            print(f"[失败]   {model}  {type(exc).__name__}: {str(exc)[:200]}\n")

    if failed:
        print("以下模型下载失败：")
        for model, exc in failed:
            print(f"  - {model}: {type(exc).__name__}")
        return 1

    print("全部完成。运行时的 HF_HOME 应指向：")
    print(f"    {target}")
    print("（.env 里的 HF_HOME 已经按这个值配置好）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

