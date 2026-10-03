"""네이버 블로그 글쓰기 자동화 (스마트에디터 ONE)."""

import asyncio
import logging
import sys
from typing import Any, Dict, Optional

from playwright.async_api import Frame, Page, TimeoutError as PlaywrightTimeout

from ..config import config
from .image_upload import upload_image
from .selectors import (
    EDITOR_CATEGORY_BUTTON,
    EDITOR_CATEGORY_ITEM,
    EDITOR_HELP_CLOSE,
    EDITOR_POPUP_CANCEL,
    EDITOR_PUBLISH_CONFIRM,
    EDITOR_PUBLISH_LAYER,
    EDITOR_PUBLISH_OPEN,
    EDITOR_ROOT,
    EDITOR_SAVE_BUTTON,
    EDITOR_TAG_INPUT,
    EDITOR_TEXT_PARAGRAPH,
    EDITOR_TITLE,
    EDITOR_TOAST,
)

logger = logging.getLogger(__name__)

WRITE_ENTRY_URL = "https://blog.naver.com/GoBlogWrite.naver"
DOCUMENT_END_KEY = "Meta+ArrowDown" if sys.platform == "darwin" else "Control+End"


class NaverBlogPostError(Exception):
    """네이버 블로그 글쓰기 관련 에러."""

    pass


async def get_editor_frame(page: Page, timeout: int = 30000) -> Frame:
    """스마트에디터 ONE이 로드된 Frame을 찾습니다.

    글쓰기 페이지는 진입 경로에 따라 에디터가 최상위 문서에 있거나
    iframe#mainFrame 안에 있으므로 모든 프레임을 확인합니다.

    Raises:
        NaverBlogPostError: 에디터를 찾지 못한 경우
    """
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        for frame in page.frames:
            try:
                if await frame.locator(EDITOR_ROOT).count() > 0:
                    return frame
            except Exception:
                continue
        await asyncio.sleep(0.5)

    raise NaverBlogPostError(f"에디터를 찾을 수 없습니다. 현재 URL: {page.url}")


async def navigate_to_post_write_page(
    page: Page, blog_id: Optional[str] = None, timeout: int = 30000
) -> Frame:
    """글쓰기 페이지로 이동하고 에디터 Frame을 반환합니다.

    Raises:
        NaverBlogPostError: 페이지 이동 실패 또는 로그인 만료
    """
    blog_id = blog_id or config.NAVER_BLOG_ID
    url = f"https://blog.naver.com/{blog_id}/postwrite" if blog_id else WRITE_ENTRY_URL

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except PlaywrightTimeout as e:
        raise NaverBlogPostError(f"글쓰기 페이지 이동 시간 초과: {str(e)}")

    if "nid.naver.com" in page.url:
        raise NaverBlogPostError(
            "로그인 세션이 만료되었습니다. `uv run naver-blog-mcp login`을 다시 실행해 주세요."
        )

    frame = await get_editor_frame(page, timeout)
    await frame.locator(EDITOR_TITLE).first.wait_for(state="visible", timeout=timeout)
    await dismiss_editor_popups(frame)
    logger.info(f"글쓰기 페이지로 이동: {page.url}")
    return frame


async def dismiss_editor_popups(frame: Frame) -> None:
    """에디터 진입 시 뜨는 팝업을 닫습니다.

    - "작성 중인 글이 있습니다" 팝업: 취소를 눌러 새 글로 시작
    - 도움말 패널: 닫기
    """
    # 팝업은 에디터 로드 직후 약간 늦게 뜬다
    await asyncio.sleep(1.5)
    for selector in (EDITOR_POPUP_CANCEL, EDITOR_HELP_CLOSE):
        try:
            button = frame.locator(selector).first
            if await button.count() > 0 and await button.is_visible():
                await button.click(timeout=3000)
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"팝업 닫기 실패 (무시): {selector} - {e}")


async def type_text(page: Page, text: str) -> None:
    """현재 커서 위치에 여러 줄 텍스트를 입력합니다."""
    lines = text.replace("\r\n", "\n").split("\n")
    for index, line in enumerate(lines):
        if line:
            await page.keyboard.insert_text(line)
        if index < len(lines) - 1:
            await page.keyboard.press("Enter")
    await asyncio.sleep(0.3)


async def fill_post_title(page: Page, frame: Frame, title: str) -> None:
    """블로그 글 제목을 입력합니다.

    Raises:
        NaverBlogPostError: 제목 입력 실패 시
    """
    try:
        await frame.locator(EDITOR_TITLE).first.click()
        await type_text(page, title.replace("\n", " "))
    except Exception as e:
        raise NaverBlogPostError(f"제목 입력 중 오류: {str(e)}")


async def focus_document_end(page: Page, frame: Frame) -> None:
    """커서를 본문 맨 끝으로 옮깁니다."""
    paragraph = frame.locator(EDITOR_TEXT_PARAGRAPH).last
    await paragraph.scroll_into_view_if_needed()
    await paragraph.click()
    await page.keyboard.press(DOCUMENT_END_KEY)
    await asyncio.sleep(0.2)


async def fill_post_blocks(page: Page, frame: Frame, blocks: list[dict]) -> int:
    """블록(텍스트/이미지)을 순서대로 본문에 입력합니다.

    Returns:
        업로드한 이미지 수

    Raises:
        NaverBlogPostError: 본문 입력 실패 시
    """
    images_uploaded = 0
    try:
        for index, block in enumerate(blocks):
            await focus_document_end(page, frame)
            if block["type"] == "image":
                await upload_image(page, frame, block["path"])
                images_uploaded += 1
            else:
                # 앞 블록과 문단을 분리한다
                if index > 0 and blocks[index - 1]["type"] == "text":
                    await page.keyboard.press("Enter")
                await type_text(page, block["text"])
        return images_uploaded
    except NaverBlogPostError:
        raise
    except Exception as e:
        raise NaverBlogPostError(f"본문 입력 중 오류: {str(e)}")


async def save_draft(page: Page, frame: Frame) -> Dict[str, Any]:
    """글을 임시저장합니다.

    Raises:
        NaverBlogPostError: 저장 버튼을 찾지 못했거나 저장 확인에 실패한 경우
    """
    button = frame.locator(EDITOR_SAVE_BUTTON).first
    if await button.count() == 0:
        raise NaverBlogPostError("저장 버튼을 찾을 수 없습니다.")

    await button.click()
    try:
        await frame.locator(EDITOR_TOAST).first.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        raise NaverBlogPostError("임시저장 완료를 확인하지 못했습니다.")

    return {
        "success": True,
        "published": False,
        "message": "임시저장했습니다. 블로그 글쓰기 화면의 '저장' 목록에서 확인하세요.",
        "post_url": None,
    }


async def _select_category(frame: Frame, category: str) -> bool:
    """발행 설정 레이어에서 카테고리를 선택합니다."""
    try:
        await frame.locator(EDITOR_CATEGORY_BUTTON).first.click(timeout=5000)
        item = frame.locator(EDITOR_CATEGORY_ITEM).filter(has_text=category).first
        await item.click(timeout=5000)
        return True
    except Exception as e:
        logger.warning(f"카테고리 선택 실패: {category} - {e}")
        return False


async def _fill_tags(page: Page, frame: Frame, tags: list[str]) -> bool:
    """발행 설정 레이어에서 태그를 입력합니다."""
    try:
        tag_input = frame.locator(EDITOR_TAG_INPUT).first
        await tag_input.click(timeout=5000)
        for tag in tags:
            cleaned = tag.strip().lstrip("#").replace(" ", "")
            if not cleaned:
                continue
            await page.keyboard.insert_text(cleaned)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.2)
        return True
    except Exception as e:
        logger.warning(f"태그 입력 실패: {e}")
        return False


async def publish_post(
    page: Page,
    frame: Frame,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    timeout: int = 30000,
) -> Dict[str, Any]:
    """글을 공개 발행합니다.

    Raises:
        NaverBlogPostError: 발행 실패 시
    """
    warnings: list[str] = []
    try:
        await frame.locator(EDITOR_PUBLISH_OPEN).first.click(timeout=10000)
        await frame.locator(EDITOR_PUBLISH_LAYER).first.wait_for(
            state="visible", timeout=10000
        )

        if category and not await _select_category(frame, category):
            warnings.append(f"카테고리 '{category}'를 선택하지 못해 기본 카테고리로 발행했습니다.")
        if tags and not await _fill_tags(page, frame, tags):
            warnings.append("태그를 입력하지 못했습니다.")

        await frame.locator(EDITOR_PUBLISH_CONFIRM).first.click(timeout=10000)
        await page.wait_for_url(
            lambda url: "postwrite" not in url.lower() and "redirect=write" not in url.lower(),
            timeout=timeout,
        )
    except PlaywrightTimeout as e:
        raise NaverBlogPostError(f"발행 시간 초과: {str(e)}")
    except Exception as e:
        raise NaverBlogPostError(f"발행 중 오류: {str(e)}")

    logger.info(f"발행 완료: {page.url}")
    return {
        "success": True,
        "published": True,
        "message": "글이 발행되었습니다.",
        "post_url": page.url,
        "warnings": warnings,
    }


async def create_blog_post(
    page: Page,
    title: str,
    blocks: list[dict],
    blog_id: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    publish: bool = False,
) -> Dict[str, Any]:
    """
    네이버 블로그에 새 글을 작성하는 전체 프로세스.

    Args:
        page: Playwright Page 객체 (로그인된 상태여야 함)
        title: 글 제목
        blocks: 순서대로 입력할 블록 목록
            [{"type": "text", "text": str} | {"type": "image", "path": str}, ...]
        blog_id: 블로그 ID (옵션)
        category: 카테고리 이름 (발행 시 적용)
        tags: 태그 목록 (발행 시 적용)
        publish: True면 공개 발행, False면 임시저장

    Returns:
        {
            "success": bool,
            "published": bool,
            "message": str,
            "post_url": str | None,
            "title": str,
            "images_uploaded": int,
            "warnings": list[str],
        }

    Raises:
        NaverBlogPostError: 글 작성 실패 시
    """
    frame = await navigate_to_post_write_page(page, blog_id)
    await fill_post_title(page, frame, title)
    images_uploaded = await fill_post_blocks(page, frame, blocks)

    if publish:
        result = await publish_post(page, frame, category, tags)
    else:
        result = await save_draft(page, frame)
        result["warnings"] = (
            ["카테고리와 태그는 발행할 때 설정됩니다. 임시저장에는 반영되지 않습니다."]
            if category or tags
            else []
        )

    result["title"] = title
    result["images_uploaded"] = images_uploaded
    return result
