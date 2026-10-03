"""네이버 로그인 자동화."""

import asyncio
import logging
import os
from pathlib import Path

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

from .selectors import (
    LOGIN_BTN,
    LOGIN_ID_INPUT,
    LOGIN_PW_INPUT,
    LOGIN_STAY_CHECKBOX,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
AUTH_COOKIE_NAMES = {"NID_AUT", "NID_SES"}


class NaverLoginError(Exception):
    """네이버 로그인 관련 에러."""

    pass


class CaptchaDetectedError(NaverLoginError):
    """CAPTCHA 감지됨."""

    pass


class InvalidCredentialsError(NaverLoginError):
    """잘못된 로그인 정보."""

    pass


async def has_auth_cookies(context: BrowserContext) -> bool:
    """네이버 로그인 쿠키(NID_AUT, NID_SES)가 모두 있는지 확인합니다."""
    cookies = await context.cookies("https://nid.naver.com")
    names = {cookie["name"] for cookie in cookies}
    return AUTH_COOKIE_NAMES.issubset(names)


async def save_session(context: BrowserContext, storage_state_path: str) -> None:
    """세션을 파일로 저장합니다. 로그인 쿠키가 담기므로 소유자만 읽을 수 있게 합니다."""
    path = Path(storage_state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(path))
    os.chmod(path, 0o600)


async def login_manually(
    page: Page,
    storage_state_path: str,
    timeout_seconds: int = 300,
) -> dict:
    """
    브라우저 창에서 사용자가 직접 로그인할 때까지 기다린 뒤 세션을 저장합니다.

    비밀번호를 파일이나 환경변수에 두지 않아도 되고, 2단계 인증과 CAPTCHA도
    사용자가 직접 처리할 수 있습니다.

    Raises:
        NaverLoginError: 제한 시간 안에 로그인이 완료되지 않은 경우
    """
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    logger.info(f"브라우저 창에서 네이버에 로그인해 주세요. ({timeout_seconds}초 대기)")

    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if await has_auth_cookies(page.context) and "nidlogin" not in page.url:
            await save_session(page.context, storage_state_path)
            return {
                "success": True,
                "message": "로그인에 성공했습니다.",
                "storage_state_path": storage_state_path,
            }
        await asyncio.sleep(1)

    raise NaverLoginError(
        f"제한 시간 안에 로그인이 완료되지 않았습니다. (마지막 URL: {page.url.split('?')[0]})"
    )


async def login_to_naver(
    page: Page,
    user_id: str,
    password: str,
    storage_state_path: str,
    headless: bool = True,
) -> dict:
    """
    아이디/비밀번호로 네이버에 로그인하고 세션을 저장합니다.

    네이버는 자동 입력에 CAPTCHA를 자주 띄우므로 `login_manually`를 권장합니다.

    Raises:
        CaptchaDetectedError: CAPTCHA가 감지된 경우
        InvalidCredentialsError: 로그인 정보가 잘못된 경우
        NaverLoginError: 기타 로그인 에러
    """
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.fill(LOGIN_ID_INPUT, user_id)
        await asyncio.sleep(0.5)
        await page.fill(LOGIN_PW_INPUT, password)
        await asyncio.sleep(0.5)

        # 로그인 상태 유지: 세션 쿠키 수명을 늘린다
        try:
            await page.locator(LOGIN_STAY_CHECKBOX).check(force=True, timeout=2000)
        except Exception:
            logger.debug("로그인 상태 유지 체크 실패 (무시)")

        selectors = LOGIN_BTN if isinstance(LOGIN_BTN, list) else [LOGIN_BTN]
        for selector in selectors:
            try:
                await page.click(selector, timeout=3000)
                break
            except PlaywrightTimeout:
                continue
        else:
            raise NaverLoginError("로그인 버튼을 찾을 수 없습니다.")

        try:
            await page.wait_for_url(
                lambda url: "nidlogin" not in url, timeout=10000
            )
        except PlaywrightTimeout:
            if await page.locator("iframe[src*='captcha'], #captcha").count() > 0:
                if headless:
                    raise CaptchaDetectedError(
                        "CAPTCHA가 감지되었습니다. `naver-blog-mcp login`으로 직접 로그인해 주세요."
                    )
                await _wait_for_captcha_manual(page)
            else:
                error = page.locator(".error_message:visible").first
                if await error.count() > 0:
                    message = (await error.text_content() or "").strip()
                    raise InvalidCredentialsError(f"로그인 실패: {message}")
                raise NaverLoginError("로그인에 실패했습니다.")

        if not await has_auth_cookies(page.context):
            raise NaverLoginError("로그인 후 세션 쿠키를 확인할 수 없습니다.")

        await save_session(page.context, storage_state_path)
        return {
            "success": True,
            "message": "로그인에 성공했습니다.",
            "storage_state_path": storage_state_path,
        }

    except NaverLoginError:
        raise
    except PlaywrightTimeout as e:
        raise NaverLoginError(f"로그인 시간 초과: {str(e)}")
    except Exception as e:
        raise NaverLoginError(f"로그인 중 오류 발생: {str(e)}")


async def _wait_for_captcha_manual(page: Page, timeout: int = 120000) -> None:
    """사용자가 수동으로 CAPTCHA를 풀고 로그인을 마칠 때까지 대기합니다."""
    logger.warning("CAPTCHA가 감지되었습니다. 브라우저에서 직접 풀어주세요.")
    try:
        await page.wait_for_url(lambda url: "nidlogin" not in url, timeout=timeout)
    except PlaywrightTimeout:
        raise NaverLoginError("CAPTCHA 해결 시간 초과")


async def verify_login_session(page: Page) -> bool:
    """
    현재 세션이 로그인 상태인지 확인합니다.

    로그인 쿠키가 있고, 로그인이 필요한 글쓰기 진입 URL이 로그인 페이지로
    튕기지 않으면 유효한 세션으로 봅니다.
    """
    try:
        if not await has_auth_cookies(page.context):
            return False
        await page.goto(
            "https://blog.naver.com/GoBlogWrite.naver",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        return "nid.naver.com" not in page.url
    except Exception:
        return False


async def logout_from_naver(page: Page) -> None:
    """네이버에서 로그아웃합니다."""
    try:
        await page.goto("https://nid.naver.com/nidlogin.logout")
        await asyncio.sleep(1)
    except Exception as e:
        raise NaverLoginError(f"로그아웃 중 오류 발생: {str(e)}")
