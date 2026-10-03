# 네이버 블로그 MCP 서버

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/Playwright-1.55.0-green.svg)](https://playwright.dev/)
[![MCP](https://img.shields.io/badge/MCP-1.20.0+-orange.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Playwright 기반 네이버 블로그 자동화를 위한 Model Context Protocol (MCP) 서버입니다. Claude가 네이버 블로그에 글을 작성하고 관리할 수 있도록 합니다.

> 이 저장소는 [space-cap/naver-blog-mcp](https://github.com/space-cap/naver-blog-mcp)의 포크입니다.
> 아래 "포크에서 바뀐 점"을 먼저 읽어 주세요.

## 포크에서 바뀐 점

- **임시저장이 기본값**: `publish`를 생략하면 임시저장하고, `publish=true`일 때만 공개 발행합니다. (원본은 `publish=false`여도 발행 버튼을 눌렀습니다.)
- **사진과 글 순서 배치**: `blocks` 인자로 사진과 문단을 원하는 순서로 넣습니다. (원본은 사진을 올린 뒤 글쓰기 페이지를 새로 열어 사진이 남지 않았습니다.)
- **카테고리·태그 적용**: 발행할 때 실제로 반영합니다. (원본은 인자만 받고 무시했습니다.)
- **비밀번호 없는 로그인**: `naver-blog-mcp login`으로 브라우저에서 직접 로그인하고 세션만 저장합니다. 24시간마다 강제 재로그인하던 로직을 없앴습니다.
- **MCP 통신 안정화**: stdout으로 나가던 `print` 로그를 없앴습니다. (stdio MCP 프로토콜을 깨뜨립니다.)
- **카테고리 조회 수정**: 빈 목록을 돌려주던 페이지 파싱을 카테고리 API 호출로 바꿨습니다.
- **경로 고정**: 세션·스크린샷·Trace 경로를 실행 위치와 무관하게 프로젝트 기준 절대 경로로 씁니다. Trace는 실패한 실행만 저장합니다.
- **글 작성 자동 재시도 제거**: 재시도로 같은 글이 두 번 올라가는 것을 막습니다.

### 검증 상태 (2026-10-03, 실제 계정)

- **확인함**: 직접 로그인과 세션 재사용, 제목 입력, 글·사진 순서 배치, 사진 업로드, 임시저장, 카테고리 조회, 발행 설정 창의 카테고리·태그·발행 버튼 위치.
- **확인하지 않음**: 최종 발행 버튼을 누른 뒤의 동작(공개 글이 올라가므로 누르지 않았습니다), "작성 중인 글이 있습니다" 팝업 처리.
- 네이버 UI가 바뀌면 `src/naver_blog_mcp/automation/selectors.py`만 고치면 됩니다. `tests/manual/live_draft_check.py`로 확인할 수 있습니다.

## 설치

```bash
git clone https://github.com/choiks14/naver-blog-mcp.git
cd naver-blog-mcp
uv sync
cp .env.example .env
```

설치된 Google Chrome을 쓰려면 `.env`에 `BROWSER_CHANNEL=chrome`을 넣습니다. 번들 Chromium을 쓰려면 `uv run playwright install chromium`을 실행합니다.

## 로그인

```bash
uv run naver-blog-mcp login
```

브라우저 창이 뜨면 직접 로그인합니다(2단계 인증·CAPTCHA 포함). '로그인 상태 유지'를 체크하면 세션이 오래갑니다. 로그인 쿠키는 `playwright-state/auth.json`에 저장되며 Git에 올라가지 않습니다. 세션이 만료되면 Tool이 재로그인을 안내합니다.

`.env`에 `NAVER_BLOG_ID`와 `NAVER_BLOG_PASSWORD`를 넣으면 세션 만료 시 자동 로그인을 시도하지만, 네이버가 CAPTCHA를 띄우는 경우가 많아 권장하지 않습니다.

## MCP 등록

Claude Code:

```bash
claude mcp add naver-blog -- uv run --directory /path/to/naver-blog-mcp naver-blog-mcp
```

Claude Desktop은 `claude_desktop_config.json` 예시를 참고하세요.

## MCP Tools

### `naver_blog_create_post`

| 인자 | 설명 |
|---|---|
| `title` (필수) | 글 제목 |
| `blocks` | 본문 블록 목록. `{"type":"text","text":"..."}` 또는 `{"type":"image","path":"/절대/경로.jpg"}` |
| `content` | 일반 텍스트 본문. `blocks`가 없을 때 사용 |
| `images` | `content` 앞에 넣을 이미지 경로 목록. `blocks`가 없을 때 사용 |
| `category` | 카테고리 이름 (발행 시 적용) |
| `tags` | 태그 목록 (발행 시 적용) |
| `publish` | `true`면 공개 발행, 기본 `false`는 임시저장 |

```json
{
  "title": "10월 3일 기록",
  "blocks": [
    {"type": "image", "path": "/Users/me/photos/breakfast.jpg"},
    {"type": "text", "text": "아침은 간단하게 먹었다."},
    {"type": "image", "path": "/Users/me/photos/boxing.jpg"},
    {"type": "text", "text": "저녁에는 복싱."}
  ]
}
```

이미지는 JPG, PNG, GIF, BMP, HEIC, HEIF, WebP를 지원하고 장당 10MB까지입니다.

### `naver_blog_list_categories`

블로그의 카테고리 목록(이름, 번호, 글 수)을 조회합니다.

## 개발

```bash
uv run pytest                                   # 브라우저 없이 도는 단위 테스트
uv run python tests/manual/live_draft_check.py  # 실제 계정에 임시저장 글 생성 (발행 안 함)
```

`tests/manual/`의 스크립트는 실제 네이버에 접속하므로 `pytest`에서 제외되어 있습니다. 실패한 실행의 스크린샷과 Trace는 `playwright-state/`에 남습니다.

## 주의사항

- 공식 API가 아니라 브라우저 자동화이므로 네이버 UI가 바뀌면 동작하지 않을 수 있습니다.
- 과도한 자동 게시는 네이버 이용약관 위반으로 제재될 수 있습니다.
- `.env`와 `playwright-state/`는 Git에 커밋하지 마세요.
- 네이버 블로그는 Markdown을 지원하지 않습니다. 본문은 일반 텍스트로 입력됩니다.

## 라이선스

MIT License. 원본: [space-cap/naver-blog-mcp](https://github.com/space-cap/naver-blog-mcp)
