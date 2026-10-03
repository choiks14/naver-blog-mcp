"""네이버 블로그 카테고리 관련 자동화 기능."""

import logging
import re
from typing import Any, Dict, Optional

from playwright.async_api import Page

from ..config import config

logger = logging.getLogger(__name__)

CATEGORY_API_URL = "https://m.blog.naver.com/api/blogs/{blog_id}/category-list"
WRITE_ENTRY_URL = "https://blog.naver.com/GoBlogWrite.naver"


def parse_category_response(payload: dict, blog_id: str) -> list[dict]:
    """카테고리 API 응답을 Tool 결과 형식으로 변환합니다.

    구분선과 "전체보기"(categoryNo 0)는 제외합니다.
    """
    categories = []
    for item in (payload.get("result") or {}).get("mylogCategoryList") or []:
        category_no = item.get("categoryNo")
        name = (item.get("categoryName") or "").strip()
        if item.get("divisionLine") or not name or not category_no:
            continue
        categories.append(
            {
                "name": name,
                "categoryNo": str(category_no),
                "url": (
                    f"https://blog.naver.com/PostList.naver"
                    f"?blogId={blog_id}&categoryNo={category_no}"
                ),
                "postCount": item.get("postCnt", 0),
                "isChild": bool(item.get("childCategory")),
            }
        )
    return categories


async def resolve_blog_id(page: Page) -> Optional[str]:
    """설정에 블로그 아이디가 없으면 글쓰기 진입 URL의 리다이렉트에서 알아냅니다."""
    if config.NAVER_BLOG_ID:
        return config.NAVER_BLOG_ID

    await page.goto(WRITE_ENTRY_URL, wait_until="domcontentloaded")
    match = re.search(r"blog\.naver\.com/([^/?#]+)", page.url)
    if match and not match.group(1).endswith(".naver"):
        return match.group(1)
    return None


async def get_categories(
    page: Page,
    blog_id: Optional[str] = None,
) -> Dict[str, Any]:
    """네이버 블로그의 카테고리 목록을 가져옵니다.

    Returns:
        {
            "success": bool,
            "message": str,
            "categories": [
                {"name": str, "categoryNo": str, "url": str,
                 "postCount": int, "isChild": bool},
                ...
            ]
        }
    """
    failure = {"success": False, "categories": []}

    try:
        blog_id = blog_id or await resolve_blog_id(page)
        if not blog_id:
            return {**failure, "message": "블로그 아이디를 확인할 수 없습니다."}

        response = await page.context.request.get(
            CATEGORY_API_URL.format(blog_id=blog_id),
            headers={"Referer": f"https://m.blog.naver.com/{blog_id}"},
        )
        if not response.ok:
            return {**failure, "message": f"카테고리 조회 실패 (HTTP {response.status})"}

        payload = await response.json()
        if not payload.get("isSuccess"):
            return {**failure, "message": "카테고리 조회 요청이 거부되었습니다."}

        categories = parse_category_response(payload, blog_id)
        logger.info(f"카테고리 {len(categories)}개 조회 완료")
        return {
            "success": True,
            "message": f"{len(categories)}개의 카테고리를 찾았습니다",
            "categories": categories,
        }

    except Exception as e:
        logger.error(f"카테고리 조회 실패: {e}", exc_info=True)
        return {**failure, "message": f"카테고리 조회 중 오류 발생: {str(e)}"}
