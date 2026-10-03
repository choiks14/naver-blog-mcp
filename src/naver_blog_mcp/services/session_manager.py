"""네이버 블로그 세션 관리자."""

import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext

from ..automation.login import (
    NaverLoginError,
    login_to_naver,
    save_session,
    verify_login_session,
)
from ..config import get_context_config

logger = logging.getLogger(__name__)


class SessionManager:
    """네이버 블로그 세션을 관리하는 클래스."""

    def __init__(
        self,
        storage_path: str,
        user_id: str = "",
        password: str = "",
    ):
        """
        세션 매니저 초기화.

        Args:
            storage_path: 세션 저장 경로
            user_id: 네이버 아이디 (자동 로그인용, 선택)
            password: 네이버 비밀번호 (자동 로그인용, 선택)
        """
        self.storage_path = storage_path
        self.user_id = user_id
        self.password = password

    def has_session_file(self) -> bool:
        """저장된 세션 파일이 있는지 확인합니다."""
        return Path(self.storage_path).exists()

    async def is_session_valid(self, context: BrowserContext) -> bool:
        """실제 네이버 페이지에 접속하여 세션 유효성을 검사합니다."""
        page = await context.new_page()
        try:
            return await verify_login_session(page)
        finally:
            await page.close()

    async def get_or_create_session(
        self, browser: Browser, headless: bool = True
    ) -> BrowserContext:
        """
        저장된 세션이 유효하면 재사용합니다.

        세션이 없거나 만료된 경우, 아이디/비밀번호가 설정되어 있으면 자동 로그인을
        시도하고, 그렇지 않으면 `naver-blog-mcp login` 실행을 안내하는 에러를 냅니다.

        Raises:
            NaverLoginError: 사용할 수 있는 세션이 없는 경우
        """
        if self.has_session_file():
            context = await browser.new_context(
                storage_state=self.storage_path, **get_context_config()
            )
            if await self.is_session_valid(context):
                logger.info(f"저장된 세션 재사용: {self.storage_path}")
                # 갱신된 쿠키를 다시 저장해 세션 수명을 늘린다
                await save_session(context, self.storage_path)
                return context
            logger.warning("저장된 세션이 만료되었습니다.")
            await context.close()

        if not (self.user_id and self.password):
            raise NaverLoginError(
                "유효한 로그인 세션이 없습니다. "
                "터미널에서 `uv run naver-blog-mcp login`을 실행해 로그인해 주세요."
            )

        context = await browser.new_context(**get_context_config())
        page = await context.new_page()
        try:
            await login_to_naver(
                page=page,
                user_id=self.user_id,
                password=self.password,
                storage_state_path=self.storage_path,
                headless=headless,
            )
            return context
        except NaverLoginError:
            await context.close()
            raise
        finally:
            if not page.is_closed():
                await page.close()

    def clear_session(self) -> None:
        """저장된 세션 파일을 삭제합니다."""
        if self.has_session_file():
            Path(self.storage_path).unlink()
            logger.info(f"세션 파일 삭제: {self.storage_path}")
