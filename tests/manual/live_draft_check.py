"""실제 네이버 블로그에 임시저장 글을 만들어 보는 수동 점검 스크립트.

공개 발행은 하지 않습니다. 먼저 `uv run naver-blog-mcp login`으로 로그인하세요.

    uv run python tests/manual/live_draft_check.py
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from naver_blog_mcp.mcp.tools import handle_create_post
from naver_blog_mcp.server import NaverBlogMCPServer


def make_test_images(directory: Path) -> list[Path]:
    paths = []
    for name, color in (("first", "tomato"), ("second", "steelblue")):
        path = directory / f"{name}.png"
        Image.new("RGB", (640, 360), color).save(path)
        paths.append(path)
    return paths


async def main() -> None:
    server = NaverBlogMCPServer()
    with tempfile.TemporaryDirectory() as tmp:
        first, second = make_test_images(Path(tmp))
        try:
            await server.initialize()
            page = await server.get_page()
            result = await handle_create_post(
                page=page,
                title=f"[자동화 점검] {datetime.now():%Y-%m-%d %H:%M}",
                blocks=[
                    {"type": "text", "text": "첫 문단입니다.\n둘째 줄입니다."},
                    {"type": "image", "path": str(first)},
                    {"type": "text", "text": "첫 사진 아래 문단입니다."},
                    {"type": "image", "path": str(second)},
                    {"type": "text", "text": "마지막 문단입니다."},
                ],
                publish=False,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            await server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
