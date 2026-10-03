"""프로젝트 설정 관리."""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env 파일 로드
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env")


def _resolve_path(value: str) -> str:
    """상대 경로를 프로젝트 루트 기준 절대 경로로 변환합니다."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return str(path)


class Config:
    """프로젝트 설정 클래스."""

    # 네이버 블로그 계정 (모두 선택 사항)
    # NAVER_BLOG_ID: 글쓰기 URL과 카테고리 조회에 사용
    # NAVER_BLOG_PASSWORD: 설정하면 세션 만료 시 자동 로그인을 시도 (권장하지 않음)
    NAVER_BLOG_ID: str = os.getenv("NAVER_BLOG_ID", "")
    NAVER_BLOG_PASSWORD: str = os.getenv("NAVER_BLOG_PASSWORD", "")

    # Playwright 설정
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "0"))
    # "chrome"으로 설정하면 설치된 Google Chrome을 사용 (비우면 번들 Chromium)
    BROWSER_CHANNEL: str = os.getenv("BROWSER_CHANNEL", "")

    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # 세션 설정
    STATE_DIR: str = _resolve_path(os.getenv("STATE_DIR", "playwright-state"))
    SESSION_STORAGE_PATH: str = _resolve_path(
        os.getenv("SESSION_STORAGE_PATH", "playwright-state/auth.json")
    )
    LOGIN_TIMEOUT_SECONDS: int = int(os.getenv("LOGIN_TIMEOUT_SECONDS", "300"))

    # Playwright 브라우저 설정
    BROWSER_ARGS: list[str] = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]

    VIEWPORT: dict[str, int] = {"width": 1440, "height": 900}

    @classmethod
    def get_browser_config(cls, headless: bool | None = None) -> dict:
        """Playwright 브라우저 설정을 반환합니다."""
        browser_config: dict = {
            "headless": cls.HEADLESS if headless is None else headless,
            "args": cls.BROWSER_ARGS,
            "slow_mo": cls.SLOW_MO,
        }
        if cls.BROWSER_CHANNEL:
            browser_config["channel"] = cls.BROWSER_CHANNEL
        return browser_config

    @classmethod
    def get_context_config(cls) -> dict:
        """Playwright 컨텍스트 설정을 반환합니다."""
        return {
            "viewport": cls.VIEWPORT,
            "locale": "ko-KR",
            "timezone_id": "Asia/Seoul",
        }


# 전역 설정 인스턴스
config = Config()


# 편의 함수
def get_browser_config(headless: bool | None = None) -> dict:
    """Playwright 브라우저 설정을 반환합니다."""
    return config.get_browser_config(headless)


def get_context_config() -> dict:
    """Playwright 컨텍스트 설정을 반환합니다."""
    return config.get_context_config()
