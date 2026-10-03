"""브라우저 없이 실행되는 단위 테스트: 블록 정규화와 이미지 검증."""

import base64
from pathlib import Path

import pytest
from PIL import Image

from naver_blog_mcp.automation.category_actions import parse_category_response
from naver_blog_mcp.automation.image_upload import (
    MAX_IMAGE_BYTES,
    decode_base64_image,
    validate_image,
)
from naver_blog_mcp.mcp.tools import TOOLS_METADATA, build_blocks, handle_create_post
from naver_blog_mcp.utils.exceptions import UploadError


def make_image(path: Path) -> Path:
    Image.new("RGB", (8, 8), "red").save(path)
    return path


def test_blocks_are_kept_in_order():
    blocks = build_blocks(
        blocks=[
            {"type": "image", "path": "/a.jpg"},
            {"type": "text", "text": "아침"},
            {"type": "image", "path": "/b.jpg"},
            {"type": "text", "text": "점심"},
        ]
    )
    assert [b["type"] for b in blocks] == ["image", "text", "image", "text"]
    assert blocks[1]["text"] == "아침"
    assert blocks[2]["path"] == "/b.jpg"


def test_legacy_arguments_put_images_before_content():
    blocks = build_blocks(content="본문", images=["/a.jpg", "/b.jpg"])
    assert blocks == [
        {"type": "image", "path": "/a.jpg"},
        {"type": "image", "path": "/b.jpg"},
        {"type": "text", "text": "본문"},
    ]


def test_blocks_take_precedence_over_content():
    blocks = build_blocks(content="무시됨", blocks=[{"type": "text", "text": "사용됨"}])
    assert blocks == [{"type": "text", "text": "사용됨"}]


def test_blank_text_blocks_are_dropped():
    blocks = build_blocks(
        blocks=[{"type": "text", "text": "  \n"}, {"type": "text", "text": "내용"}]
    )
    assert blocks == [{"type": "text", "text": "내용"}]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"content": "   "},
        {"blocks": [{"type": "text", "text": ""}]},
    ],
)
def test_empty_body_is_rejected(kwargs):
    with pytest.raises(ValueError, match="본문이 비어"):
        build_blocks(**kwargs)


def test_image_block_without_path_is_rejected():
    with pytest.raises(ValueError, match="path"):
        build_blocks(blocks=[{"type": "image"}])


def test_unknown_block_type_is_rejected():
    with pytest.raises(ValueError, match="type"):
        build_blocks(blocks=[{"type": "video", "path": "/a.mp4"}])


def test_validate_image_accepts_supported_file(tmp_path):
    validate_image(make_image(tmp_path / "ok.png"))


def test_validate_image_rejects_missing_file(tmp_path):
    with pytest.raises(UploadError, match="not found"):
        validate_image(tmp_path / "missing.jpg")


def test_validate_image_rejects_unsupported_format(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("not an image")
    with pytest.raises(UploadError, match="Unsupported"):
        validate_image(path)


def test_validate_image_rejects_oversized_file(tmp_path):
    path = tmp_path / "big.jpg"
    path.write_bytes(b"0" * (MAX_IMAGE_BYTES + 1))
    with pytest.raises(UploadError, match="too large"):
        validate_image(path)


def test_decode_base64_data_uri():
    payload = base64.b64encode(b"hello").decode()
    data, extension = decode_base64_image(f"data:image/jpeg;base64,{payload}")
    assert data == b"hello"
    assert extension == ".jpeg"


def test_create_post_defaults_to_draft():
    schema = TOOLS_METADATA["naver_blog_create_post"]["inputSchema"]
    assert schema["properties"]["publish"]["default"] is False
    assert schema["required"] == ["title"]


async def test_create_post_fails_before_opening_editor_when_image_missing(tmp_path):
    # page=None: 검증 실패 시 브라우저를 건드리지 않아야 한다
    result = await handle_create_post(
        page=None,
        title="제목",
        blocks=[{"type": "image", "path": str(tmp_path / "missing.jpg")}],
    )
    assert result["success"] is False
    assert result["published"] is False
    assert "not found" in result["message"]


def test_category_response_skips_dividers_and_all_posts():
    payload = {
        "isSuccess": True,
        "result": {
            "mylogCategoryList": [
                {"categoryName": "전체보기", "categoryNo": 0},
                {"categoryName": "다이어트", "categoryNo": 8, "postCnt": 30},
                {"categoryName": "", "categoryNo": 9, "divisionLine": True},
                {"categoryName": "복싱", "categoryNo": 12, "childCategory": True},
            ]
        },
    }
    categories = parse_category_response(payload, "myblog")
    assert [c["name"] for c in categories] == ["다이어트", "복싱"]
    assert categories[0]["categoryNo"] == "8"
    assert categories[0]["postCount"] == 30
    assert categories[0]["url"].endswith("blogId=myblog&categoryNo=8")
    assert categories[1]["isChild"] is True


def test_category_response_tolerates_missing_result():
    assert parse_category_response({"isSuccess": True}, "myblog") == []
