"""네이버 블로그 DOM 셀렉터 정의.

네이버 UI가 바뀌면 이 파일만 고치면 되도록 셀렉터를 한곳에 모아 둡니다.
발행 영역의 클래스명은 빌드마다 해시 접미사가 바뀌므로(`publish_btn__m9KHH`)
접두사 부분 일치(`[class*='publish_btn']`)로 찾습니다.
"""

# 로그인 페이지
LOGIN_ID_INPUT = "#id"
LOGIN_PW_INPUT = "#pw"
LOGIN_BTN = ["button[id^='loginBtn']:visible", ".btn_login"]
LOGIN_STAY_CHECKBOX = "#loginStay"

# 스마트에디터 ONE
EDITOR_ROOT = ".se-content"
EDITOR_TITLE = ".se-documentTitle .se-text-paragraph"
EDITOR_TEXT_PARAGRAPH = ".se-component.se-text .se-text-paragraph"

# 에디터 팝업
EDITOR_POPUP_CANCEL = ".se-popup-alert-confirm .se-popup-button-cancel"
EDITOR_HELP_CLOSE = "button.se-help-panel-close-button"
EDITOR_TOAST = ".se-toast-popup, [class*='toast']"

# 임시저장 / 발행
EDITOR_SAVE_BUTTON = "button[class*='save_btn']"
EDITOR_PUBLISH_OPEN = "button[class*='publish_btn']"
EDITOR_PUBLISH_LAYER = "[class*='layer_publish'], [class*='option_area']"
EDITOR_PUBLISH_CONFIRM = "button[class*='confirm_btn']"
EDITOR_CATEGORY_BUTTON = "button[class*='selectbox_button']"
EDITOR_CATEGORY_ITEM = "[class*='option_list'] label, [class*='option_list'] li"
EDITOR_TAG_INPUT = "input#tag-input, input[class*='tag_input']"
