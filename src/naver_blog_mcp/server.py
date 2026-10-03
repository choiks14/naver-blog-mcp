"""네이버 블로그 MCP 서버.

이 모듈은 Claude가 네이버 블로그와 상호작용할 수 있도록
MCP (Model Context Protocol) 서버를 제공합니다.
"""

import asyncio
import json
import logging
import sys
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .automation.login import login_manually
from .config import config, get_browser_config, get_context_config
from .services.session_manager import SessionManager
from .mcp.tools import (
    TOOLS_METADATA,
    handle_create_post,
    handle_list_categories,
)
from .utils.trace_manager import trace_manager

# stdout은 MCP 프로토콜 전용이므로 로그는 stderr로만 보낸다
logging.basicConfig(level=config.LOG_LEVEL, stream=sys.stderr)
logger = logging.getLogger(__name__)


class NaverBlogMCPServer:
    """네이버 블로그 MCP 서버 클래스."""

    def __init__(self):
        """서버 초기화."""
        self.server = Server("naver-blog")
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

        self.session_manager = SessionManager(
            storage_path=config.SESSION_STORAGE_PATH,
            user_id=config.NAVER_BLOG_ID,
            password=config.NAVER_BLOG_PASSWORD,
        )

        self._register_tools()

    def _register_tools(self):
        """MCP Tool들을 등록합니다."""

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Tool 호출 핸들러."""
            logger.info(f"Tool called: {name}")

            if name not in TOOLS_METADATA:
                return [TextContent(type="text", text=f"알 수 없는 Tool: {name}")]

            # 브라우저 페이지 하나를 공유하므로 호출을 직렬화한다
            async with self._lock:
                try:
                    await self.ensure_initialized()
                    await trace_manager.start_trace(self.context, name=name)
                    page = await self.get_page()

                    if name == "naver_blog_create_post":
                        result = await handle_create_post(
                            page=page,
                            title=arguments["title"],
                            content=arguments.get("content"),
                            blocks=arguments.get("blocks"),
                            category=arguments.get("category"),
                            tags=arguments.get("tags"),
                            images=arguments.get("images"),
                            publish=arguments.get("publish", False),
                        )
                    else:
                        result = await handle_list_categories(page=page)

                    await trace_manager.stop_trace(
                        self.context, success=bool(result.get("success"))
                    )
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, ensure_ascii=False, indent=2),
                        )
                    ]

                except Exception as e:
                    logger.error(f"Tool execution error: {e}", exc_info=True)
                    if self.context:
                        await trace_manager.stop_trace(self.context, success=False)
                    return [TextContent(type="text", text=f"오류 발생: {str(e)}")]

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """사용 가능한 Tool 목록을 반환합니다."""
            return [
                Tool(
                    name=tool_data["name"],
                    description=tool_data["description"],
                    inputSchema=tool_data["inputSchema"],
                )
                for tool_data in TOOLS_METADATA.values()
            ]

        logger.info(f"Registered {len(TOOLS_METADATA)} tools")

    async def initialize(self):
        """브라우저 및 세션 초기화."""
        self.playwright = await async_playwright().start()

        browser_config = get_browser_config()
        self.browser = await self.playwright.chromium.launch(**browser_config)
        logger.info(f"Browser launched (headless={browser_config['headless']})")

        self.context = await self.session_manager.get_or_create_session(
            self.browser, headless=browser_config["headless"]
        )
        logger.info("Browser context initialized")

    async def ensure_initialized(self):
        """첫 Tool 호출 시점에 브라우저를 띄웁니다.

        서버 시작 시 로그인 세션이 없어도 MCP 연결 자체는 실패하지 않고,
        Tool 결과로 로그인 안내를 돌려줄 수 있게 하기 위함입니다.
        """
        if self.context:
            return
        try:
            await self.initialize()
        except Exception:
            await self.cleanup()
            raise

    async def cleanup(self):
        """리소스 정리."""
        if self.context:
            await self.context.close()
            self.context = None

        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def get_page(self) -> Page:
        """기존 페이지를 재사용하거나 새 페이지를 생성합니다.

        Raises:
            RuntimeError: 브라우저 컨텍스트가 초기화되지 않은 경우
        """
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call initialize() first.")

        pages = self.context.pages
        if pages:
            return pages[0]
        return await self.context.new_page()

    async def run(self):
        """MCP 서버 실행."""
        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("MCP Server started successfully")
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
        finally:
            await self.cleanup()


async def run_login() -> int:
    """브라우저 창을 띄워 사용자가 직접 로그인하게 하고 세션을 저장합니다."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**get_browser_config(headless=False))
        context = await browser.new_context(**get_context_config())
        page = await context.new_page()
        try:
            print(
                "브라우저 창에서 네이버에 로그인해 주세요. "
                "'로그인 상태 유지'를 체크하면 세션이 더 오래갑니다.",
                file=sys.stderr,
            )
            result = await login_manually(
                page,
                storage_state_path=config.SESSION_STORAGE_PATH,
                timeout_seconds=config.LOGIN_TIMEOUT_SECONDS,
            )
            print(f"로그인 완료. 세션 저장: {result['storage_state_path']}", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"로그인 실패: {e}", file=sys.stderr)
            return 1
        finally:
            await browser.close()


async def async_main():
    """비동기 서버 엔트리포인트."""
    server = NaverBlogMCPServer()
    await server.run()


def main():
    """동기 서버 엔트리포인트 (CLI 진입점).

    `naver-blog-mcp`        MCP 서버 실행
    `naver-blog-mcp login`  브라우저에서 직접 로그인해 세션 저장
    """
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        sys.exit(asyncio.run(run_login()))
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
