"""
naver_blog_bot.py
네이버 블로그 자동 발행 봇 — Playwright 기반
역할: 네이버 로그인 → 글쓰기 → 발행

의존성:
  pip install playwright
  playwright install chromium
"""
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

logger = logging.getLogger(__name__)

NAVER_ID = os.getenv('NAVER_ID', '')
NAVER_PW = os.getenv('NAVER_PW', '')


# ─── 발행 이력 ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.parent
PUBLISHED_DIR = BASE_DIR / 'data' / 'naver_published'
PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)


def _log_published(title: str, post_url: str, extra: dict = None):
    import datetime
    record = {
        'title': title,
        'url': post_url,
        'published_at': datetime.datetime.now().isoformat(),
        **(extra or {}),
    }
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = PUBLISHED_DIR / f'{ts}.json'
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f"발행 이력 저장: {path}")
    return record


# ─── 메인 발행 함수 ───────────────────────────────────────────────────────────

def publish_to_naver(
    title: str,
    html_content: str,
    tags: list[str] = None,
    category_name: str = '',
    headless: bool = True,
) -> str:
    """
    네이버 블로그에 글을 발행합니다.

    Parameters
    ----------
    title        : 포스트 제목
    html_content : 발행할 HTML 본문 (네이버 스마트에디터 ONE 소스 입력)
    tags         : 태그 목록 (최대 10개)
    category_name: 카테고리 이름 (없으면 기본 카테고리)
    headless     : True = 브라우저 창 숨김

    Returns
    -------
    발행된 포스트 URL (실패 시 빈 문자열)
    """
    if not NAVER_ID or not NAVER_PW:
        logger.error("NAVER_ID / NAVER_PW 환경변수 미설정")
        return ''

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("playwright 미설치 — pip install playwright && playwright install chromium")
        return ''

    tags = tags or []
    post_url = ''

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            locale='ko-KR',
        )
        page = context.new_page()

        try:
            # ── 1. 네이버 로그인 ──────────────────────────────────────────────
            logger.info("네이버 로그인 시작")
            page.goto('https://nid.naver.com/nidlogin.login', wait_until='domcontentloaded')
            page.wait_for_selector('#id', timeout=15000)

            # JS로 값 주입 (자동화 감지 우회)
            page.evaluate(
                f"document.querySelector('#id').value = '{NAVER_ID}'"
            )
            page.evaluate(
                f"document.querySelector('#pw').value = '{NAVER_PW}'"
            )
            page.click('.btn_login')

            # 로그인 성공 확인 (네이버 메인 또는 캡차 페이지)
            try:
                page.wait_for_url('https://www.naver.com/**', timeout=10000)
                logger.info("로그인 성공")
            except PWTimeout:
                # 캡차 또는 추가 인증 페이지
                current = page.url
                logger.warning(f"로그인 후 예상치 못한 페이지: {current}")
                if 'captcha' in current or 'nidlogin' in current:
                    logger.error("캡차 또는 2단계 인증 발생 — headless=False 로 재시도 필요")
                    browser.close()
                    return ''

            # ── 2. 블로그 글쓰기 페이지 이동 ─────────────────────────────────
            logger.info("글쓰기 페이지 이동")
            write_url = f'https://blog.naver.com/PostWriteForm.naver?blogId={NAVER_ID}'
            page.goto(write_url, wait_until='domcontentloaded')
            page.wait_for_timeout(3000)

            # ── 3. 제목 입력 ──────────────────────────────────────────────────
            logger.info(f"제목 입력: {title}")
            _fill_title(page, title)

            # ── 4. HTML 소스 입력 ─────────────────────────────────────────────
            logger.info("HTML 본문 입력")
            _fill_html_body(page, html_content)

            # ── 5. 태그 입력 ──────────────────────────────────────────────────
            if tags:
                logger.info(f"태그 입력: {tags}")
                _fill_tags(page, tags[:10])

            # ── 6. 카테고리 설정 ──────────────────────────────────────────────
            if category_name:
                _set_category(page, category_name)

            # ── 7. 발행 ───────────────────────────────────────────────────────
            logger.info("발행 버튼 클릭")
            post_url = _click_publish(page)

            if post_url:
                logger.info(f"발행 완료: {post_url}")
                _log_published(title, post_url, {'tags': tags})
            else:
                logger.warning("발행 URL을 확인하지 못했습니다 (수동 확인 필요)")

        except Exception as e:
            logger.error(f"네이버 블로그 발행 오류: {e}", exc_info=True)
            # 스크린샷 저장 (디버깅용)
            try:
                ss_path = BASE_DIR / 'logs' / 'naver_error.png'
                page.screenshot(path=str(ss_path))
                logger.info(f"에러 스크린샷 저장: {ss_path}")
            except Exception:
                pass
        finally:
            context.close()
            browser.close()

    return post_url


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _fill_title(page, title: str):
    """제목 입력란 채우기"""
    selectors = [
        'input[placeholder*="제목"]',
        '#subject',
        '.se-title-input',
        'textarea[name="subject"]',
    ]
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=5000)
            if el:
                el.click()
                el.fill(title)
                return
        except Exception:
            continue

    # SmartEditor ONE iframe 내부 제목
    try:
        frame = page.frame_locator('iframe[name="mainFrame"]').first
        el = frame.locator('.se-title-input, input[placeholder*="제목"]').first
        el.click()
        el.fill(title)
    except Exception as e:
        logger.warning(f"제목 입력 실패 (계속 진행): {e}")


def _fill_html_body(page, html_content: str):
    """
    SmartEditor ONE에 HTML 직접 입력.
    '도구 > HTML' 메뉴 또는 소스 편집 모드를 활성화하여 붙여넣기.
    """
    try:
        # 방법 A: 상단 메뉴 '도구' 클릭 → 'HTML'
        _try_html_via_menu(page, html_content)
        return
    except Exception as e:
        logger.debug(f"방법A 실패: {e}")

    try:
        # 방법 B: 에디터 본문 영역에 직접 JS inject
        _try_html_via_js(page, html_content)
    except Exception as e:
        logger.warning(f"방법B 실패: {e} — 본문이 비어있을 수 있습니다")


def _try_html_via_menu(page, html_content: str):
    """상단 메뉴 '도구 > HTML' 경로로 소스 편집 모달 열기"""
    from playwright.sync_api import TimeoutError as PWTimeout

    # '도구' 메뉴
    try:
        page.click('button:has-text("도구")', timeout=5000)
        page.wait_for_timeout(500)
    except PWTimeout:
        # 메뉴 텍스트가 다를 경우
        page.click('[title="도구"], .se-toolbar-item:has-text("도구")', timeout=3000)
        page.wait_for_timeout(500)

    # 'HTML' 항목
    page.click('li:has-text("HTML"), button:has-text("HTML")', timeout=5000)
    page.wait_for_timeout(1000)

    # 모달 내 텍스트에어리어 또는 코드미러 에디터
    try:
        textarea = page.wait_for_selector('textarea.se-html-editor-text', timeout=5000)
        textarea.fill(html_content)
    except PWTimeout:
        # CodeMirror 기반 에디터
        cm = page.wait_for_selector('.CodeMirror, .cm-editor', timeout=5000)
        cm.click()
        page.keyboard.press('Control+a')
        page.keyboard.type(html_content)

    # 확인 버튼
    page.click('button:has-text("확인"), button:has-text("적용")', timeout=5000)
    page.wait_for_timeout(1000)


def _try_html_via_js(page, html_content: str):
    """JS로 에디터 iframe 내부 body에 직접 innerHTML 주입 (fallback)"""
    escaped = html_content.replace('`', '\\`')
    injected = page.evaluate(f"""
        (() => {{
            // SmartEditor ONE contenteditable 찾기
            const frames = document.querySelectorAll('iframe');
            for (const f of frames) {{
                try {{
                    const body = f.contentDocument.querySelector(
                        '.se-content, [contenteditable="true"]'
                    );
                    if (body) {{
                        body.innerHTML = `{escaped}`;
                        return true;
                    }}
                }} catch(e) {{}}
            }}
            return false;
        }})()
    """)
    if not injected:
        raise RuntimeError("JS inject: contenteditable 요소를 찾지 못했습니다")


def _fill_tags(page, tags: list[str]):
    """태그 입력"""
    selectors = [
        'input[placeholder*="태그"]',
        '.se-tag-input input',
        '#tagInput',
    ]
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=5000)
            if el:
                for tag in tags:
                    el.click()
                    el.fill(tag)
                    el.press('Enter')
                    page.wait_for_timeout(300)
                return
        except Exception:
            continue
    logger.debug("태그 입력 요소를 찾지 못했습니다 (건너뜀)")


def _set_category(page, category_name: str):
    """카테고리 드롭다운 선택"""
    try:
        page.click('button.category, select[name="categoryNo"]', timeout=5000)
        page.wait_for_timeout(500)
        page.click(f'li:has-text("{category_name}"), option:has-text("{category_name}")',
                   timeout=5000)
    except Exception as e:
        logger.debug(f"카테고리 설정 실패 (건너뜀): {e}")


def _click_publish(page) -> str:
    """발행 버튼 클릭 후 포스트 URL 반환"""
    from playwright.sync_api import TimeoutError as PWTimeout

    publish_selectors = [
        'button:has-text("발행")',
        '.btn_post:has-text("발행")',
        '#publishBtn',
    ]
    for sel in publish_selectors:
        try:
            page.click(sel, timeout=5000)
            break
        except PWTimeout:
            continue

    # 발행 확인 모달이 뜨는 경우
    try:
        page.click('button:has-text("발행"), .btn_confirm:has-text("확인")', timeout=5000)
    except PWTimeout:
        pass

    # 발행 완료 후 URL 확인 (포스트 페이지로 이동)
    try:
        page.wait_for_url('**/PostView.naver**', timeout=15000)
        return page.url
    except PWTimeout:
        pass

    try:
        page.wait_for_url(f'**/blog.naver.com/{NAVER_ID}/**', timeout=10000)
        return page.url
    except PWTimeout:
        pass

    return page.url  # 현재 URL 반환 (확인 불가 시)


# ─── 직접 실행 테스트 ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')
    sample_html = """
    <h2>테스트 포스트</h2>
    <p>네이버 블로그 자동 발행 테스트입니다.</p>
    <p>두 번째 단락입니다.</p>
    """
    url = publish_to_naver(
        title='[자동발행 테스트]',
        html_content=sample_html,
        tags=['자동발행', '테스트', 'AI블로그'],
        headless=False,  # 테스트는 브라우저 보이게
    )
    print(f"발행 URL: {url or '(실패)'}")
