"""이미지 업로드 자동화 함수.

이 모듈은 네이버 블로그 글쓰기 에디터에서 이미지를 업로드하는
Playwright 자동화 함수를 제공합니다.
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Union

from playwright.async_api import Frame, Page, TimeoutError as PlaywrightTimeoutError

from ..utils.exceptions import ElementNotFoundError, TimeoutError, UploadError

logger = logging.getLogger(__name__)


IMAGE_BUTTON_SELECTORS = [
    "button[data-name='image']",
    "button.se-image-toolbar-button",
]

# 에디터 본문에 삽입된 이미지 컴포넌트
IMAGE_COMPONENT_SELECTOR = ".se-component.se-image"

SUPPORTED_FORMATS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".heif", ".webp"]
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def validate_image(image_path: Path) -> None:
    """이미지 파일의 존재 여부, 크기, 포맷을 검증합니다.

    Raises:
        UploadError: 검증 실패
    """
    if not image_path.is_file():
        raise UploadError(
            f"Image file not found: {image_path}",
            details={"path": str(image_path)},
        )

    file_size = image_path.stat().st_size
    if file_size > MAX_IMAGE_BYTES:
        raise UploadError(
            f"Image file too large: {file_size / 1024 / 1024:.2f}MB (max 10MB)",
            details={"path": str(image_path), "size": file_size},
        )

    if image_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise UploadError(
            f"Unsupported image format: {image_path.suffix}",
            details={"path": str(image_path), "format": image_path.suffix},
        )


async def count_images(frame: Frame) -> int:
    """에디터 본문에 삽입된 이미지 개수를 반환합니다."""
    return await frame.locator(IMAGE_COMPONENT_SELECTOR).count()


async def wait_for_upload_complete(
    frame: Frame,
    initial_count: int,
    timeout: int = 60000,
) -> None:
    """새 이미지 컴포넌트가 삽입되고 서버 업로드가 끝날 때까지 대기합니다.

    Raises:
        TimeoutError: 업로드 타임아웃
    """
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        if await count_images(frame) > initial_count:
            # 업로드 중에는 blob:/data: 미리보기이고, 완료되면 서버 URL로 바뀐다
            pending = await frame.locator(
                f"{IMAGE_COMPONENT_SELECTOR} img[src^='blob:'], "
                f"{IMAGE_COMPONENT_SELECTOR} img[src^='data:']"
            ).count()
            if pending == 0:
                return
        await asyncio.sleep(0.3)

    raise TimeoutError(
        "Upload completion timeout",
        details={"timeout": timeout, "selector": IMAGE_COMPONENT_SELECTOR},
    )


async def upload_image(
    page: Page,
    frame: Frame,
    image_path: Union[str, Path],
) -> dict:
    """현재 커서 위치에 이미지 한 장을 업로드합니다.

    글쓰기 페이지가 열려 있고 커서가 본문에 있어야 합니다.

    Args:
        page: Playwright Page 객체
        frame: 에디터가 있는 Frame
        image_path: 이미지 파일 경로

    Returns:
        {"success": True, "file": str, "message": str}

    Raises:
        UploadError: 이미지 업로드 실패
        ElementNotFoundError: 사진 버튼을 찾을 수 없는 경우
    """
    image_path = Path(image_path).expanduser()
    validate_image(image_path)

    button = None
    for selector in IMAGE_BUTTON_SELECTORS:
        candidate = frame.locator(selector).first
        if await candidate.count() > 0:
            button = candidate
            break
    if button is None:
        raise ElementNotFoundError(
            "Image button not found",
            details={"selectors": IMAGE_BUTTON_SELECTORS},
        )

    initial_count = await count_images(frame)

    try:
        async with page.expect_file_chooser(timeout=10000) as chooser_info:
            await button.click()
        chooser = await chooser_info.value
        await chooser.set_files(str(image_path.resolve()))
    except PlaywrightTimeoutError as e:
        raise UploadError(
            "File chooser did not open after clicking image button",
            details={"path": str(image_path), "error": str(e)},
        )

    await wait_for_upload_complete(frame, initial_count)
    logger.info(f"Image uploaded: {image_path.name}")

    return {
        "success": True,
        "file": str(image_path),
        "message": f"Image uploaded successfully: {image_path.name}",
    }


def decode_base64_image(base64_string: str) -> tuple[bytes, str]:
    """Base64 인코딩된 이미지를 디코딩합니다.

    Args:
        base64_string: Base64 문자열 (data:image/png;base64,... 또는 순수 base64)

    Returns:
        (이미지 바이트, 파일 확장자) 튜플

    Raises:
        UploadError: 디코딩 실패
    """
    try:
        if base64_string.startswith("data:image/"):
            header, encoded = base64_string.split(",", 1)
            mime_type = header.split(";")[0].split(":")[1]
            extension = "." + mime_type.split("/")[1]
        else:
            encoded = base64_string
            extension = ".png"

        image_bytes = base64.b64decode(encoded)
        return image_bytes, extension

    except Exception as e:
        raise UploadError(
            f"Failed to decode base64 image: {str(e)}",
            details={"error": str(e)},
        )
