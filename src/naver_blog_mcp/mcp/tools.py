"""MCP Tool 정의.

이 모듈은 Claude가 호출할 수 있는 네이버 블로그 관련 Tool들을 정의합니다.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import Page

from ..automation.post_actions import create_blog_post, NaverBlogPostError
from ..automation.image_upload import validate_image
from ..automation.category_actions import get_categories
from ..utils.error_handler import handle_playwright_error
from ..utils.exceptions import NaverBlogError, UploadError

logger = logging.getLogger(__name__)

TOOLS_METADATA = {
    "naver_blog_create_post": {
        "name": "naver_blog_create_post",
        "description": (
            "네이버 블로그에 새 글을 작성합니다. 기본은 임시저장이며 "
            "publish=true일 때만 공개 발행합니다. 사진과 글을 원하는 순서로 "
            "배치하려면 blocks를 사용하세요."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "글 제목",
                },
                "content": {
                    "type": "string",
                    "description": "글 본문 (일반 텍스트). blocks를 쓰면 생략 가능",
                },
                "blocks": {
                    "type": "array",
                    "description": (
                        "본문을 순서대로 구성하는 블록 목록. content/images 대신 사용. "
                        '예: [{"type":"image","path":"/abs/a.jpg"},{"type":"text","text":"아침 식사"}]'
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["text", "image"]},
                            "text": {
                                "type": "string",
                                "description": "type=text일 때 문단 내용",
                            },
                            "path": {
                                "type": "string",
                                "description": "type=image일 때 이미지 파일의 절대 경로",
                            },
                        },
                        "required": ["type"],
                    },
                },
                "category": {
                    "type": "string",
                    "description": "카테고리 이름 (선택, 발행 시 적용)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "태그 목록 (선택, 발행 시 적용)",
                },
                "images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "content 앞에 넣을 이미지 파일 경로 목록 (선택)",
                },
                "publish": {
                    "type": "boolean",
                    "description": "true면 공개 발행, false면 임시저장 (기본: false)",
                    "default": False,
                },
            },
            "required": ["title"],
        },
    },
    "naver_blog_list_categories": {
        "name": "naver_blog_list_categories",
        "description": "네이버 블로그의 카테고리 목록을 가져옵니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


def get_tools_list() -> list[dict]:
    """등록된 Tool 목록을 반환합니다."""
    return list(TOOLS_METADATA.values())


def build_blocks(
    content: Optional[str] = None,
    images: Optional[list[str]] = None,
    blocks: Optional[list[dict]] = None,
) -> list[dict]:
    """Tool 인자를 에디터에 순서대로 입력할 블록 목록으로 정규화합니다.

    blocks가 있으면 그대로 검증해서 쓰고, 없으면 images → content 순서로 만듭니다.

    Raises:
        ValueError: 블록 형식이 잘못되었거나 본문이 비어 있는 경우
    """
    normalized: list[dict] = []

    if blocks:
        for index, block in enumerate(blocks):
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text") or ""
                if text.strip():
                    normalized.append({"type": "text", "text": text})
            elif block_type == "image":
                path = block.get("path")
                if not path:
                    raise ValueError(f"blocks[{index}]: image 블록에 path가 없습니다.")
                normalized.append({"type": "image", "path": path})
            else:
                raise ValueError(
                    f"blocks[{index}]: type은 'text' 또는 'image'여야 합니다: {block_type!r}"
                )
    else:
        for path in images or []:
            normalized.append({"type": "image", "path": path})
        if content and content.strip():
            normalized.append({"type": "text", "text": content})

    if not normalized:
        raise ValueError("본문이 비어 있습니다. content 또는 blocks를 지정하세요.")

    return normalized


# ============================================================================
# Tool Handler Functions
# ============================================================================


async def handle_create_post(
    page: Page,
    title: str,
    content: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    images: Optional[list[str]] = None,
    publish: bool = False,
    blocks: Optional[list[dict]] = None,
) -> Dict[str, Any]:
    """네이버 블로그에 새 글을 작성합니다.

    글이 중복으로 올라가는 것을 막기 위해 자동 재시도는 하지 않습니다.

    Returns:
        작업 결과 딕셔너리
        {
            "success": bool,
            "message": str,
            "published": bool,
            "post_url": str | None (발행 시),
            "title": str,
            "images_uploaded": int,
            "warnings": list[str],
        }
    """
    failure: Dict[str, Any] = {
        "success": False,
        "published": False,
        "post_url": None,
        "title": title,
        "images_uploaded": 0,
    }

    try:
        normalized = build_blocks(content=content, images=images, blocks=blocks)
        # 에디터를 열기 전에 이미지 파일을 모두 검증한다
        for block in normalized:
            if block["type"] == "image":
                validate_image(Path(block["path"]))
    except (ValueError, UploadError) as e:
        return {**failure, "message": str(e)}

    try:
        logger.info(f"글 작성 시작: {title}")
        result = await create_blog_post(
            page=page,
            title=title,
            blocks=normalized,
            category=category,
            tags=tags,
            publish=publish,
        )
        logger.info(f"글 작성 완료: {result.get('message')}")
        return result

    except (NaverBlogPostError, NaverBlogError) as e:
        logger.error(f"글 작성 실패: {e}")
        return {**failure, "message": f"글 작성 중 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        custom_error = await handle_playwright_error(e, page, "create_post")
        logger.error(f"예상치 못한 오류: {custom_error}", exc_info=True)
        return {**failure, "message": f"예상치 못한 오류: {str(custom_error)}"}


async def handle_list_categories(page: Page) -> Dict[str, Any]:
    """네이버 블로그의 카테고리 목록을 가져옵니다.

    Returns:
        작업 결과 딕셔너리
        {
            "success": bool,
            "message": str,
            "categories": [{"name": str, "url": str, "categoryNo": str}, ...]
        }
    """
    logger.info("카테고리 목록 조회 시작")

    try:
        result = await get_categories(page)

        if result["success"]:
            logger.info(f"카테고리 조회 완료: {len(result['categories'])}개")
        else:
            logger.error(f"카테고리 조회 실패: {result['message']}")

        return result

    except Exception as e:
        logger.error(f"카테고리 조회 중 예외 발생: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"카테고리 조회 실패: {str(e)}",
            "categories": [],
        }
