"""
naver_novel_converter.py
소설 에피소드 → 네이버 블로그용 HTML 변환 모듈
역할: episode dict + 소설 설정 → 네이버 스마트에디터 ONE 호환 HTML
출력: data/novels/{novel_id}/episodes/ep{N:03d}_naver.html
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent


# ─── 장르별 강조색 (네이버는 인라인 스타일만 지원) ────────────────────────────

_GENRE_ACCENT = {
    'sci-fi':    '#00bcd4',
    'thriller':  '#c0392b',
    'fantasy':   '#8e44ad',
    'romance':   '#e74c3c',
    'horror':    '#2c3e50',
    'mystery':   '#2980b9',
    'default':   '#2c3e50',
}


def _accent_color(genre: str) -> str:
    for key, color in _GENRE_ACCENT.items():
        if key in genre.lower():
            return color
    return _GENRE_ACCENT['default']


# ─── 본문 텍스트 → 네이버 HTML 단락 ────────────────────────────────────────────

def _body_to_naver_html(body_text: str) -> str:
    """
    소설 본문 → 네이버 블로그 HTML.
    - 빈 줄 기준으로 문단 분리
    - 대화문(따옴표 시작)은 이탤릭 + 색상 강조
    - HTML 특수문자 이스케이프
    """
    result = []
    for para in body_text.split('\n\n'):
        para = para.strip()
        if not para:
            continue

        lines = []
        for line in para.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 이스케이프
            line = (line
                    .replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))
            # 대화문 스타일
            if line.startswith('"') or line.startswith('"') or line.startswith('"'):
                lines.append(
                    f'<span style="color:#555;font-style:italic">{line}</span>'
                )
            else:
                lines.append(line)

        paragraph = '<br>\n'.join(lines)
        result.append(
            f'<p style="font-size:17px;line-height:2.0;'
            f'margin:0 0 20px 0;word-break:keep-all">'
            f'{paragraph}</p>'
        )

    return '\n'.join(result)


# ─── 변환 메인 함수 ──────────────────────────────────────────────────────────

def convert(
    episode: dict,
    novel_config: dict,
    prev_url: str = '',
    next_url: str = '',
    save_file: bool = True,
) -> str:
    """
    에피소드 dict + 소설 설정 → 네이버 블로그 HTML.

    Parameters
    ----------
    episode      : NovelWriter.generate_episode() 반환값
    novel_config : config/novels/{novel_id}.json 내용
    prev_url     : 이전 화 네이버 블로그 URL (없으면 '')
    next_url     : 다음 화 네이버 블로그 URL (없으면 '')
    save_file    : True이면 파일로 저장

    Returns
    -------
    네이버 블로그에 붙여넣을 HTML 문자열
    """
    novel_id  = novel_config.get('novel_id', episode.get('novel_id', 'unknown'))
    ep_num    = episode.get('episode_num', 0)
    title     = episode.get('title', f'에피소드 {ep_num}')
    body_text = episode.get('body', '')
    hook      = episode.get('hook', '')
    genre     = novel_config.get('genre', '')
    title_ko  = novel_config.get('title_ko', '')
    schedule  = novel_config.get('publish_schedule', '')
    ep_target = novel_config.get('episode_count_target', 20)

    logger.info(f"[{novel_id}] 에피소드 {ep_num} 네이버 HTML 변환 시작")

    accent = _accent_color(genre)
    body_html = _body_to_naver_html(body_text)
    today_str = datetime.now().strftime('%Y.%m.%d')

    # 이전/다음 화 링크
    prev_link = (
        f'<a href="{prev_url}" style="color:{accent};text-decoration:none">'
        f'◀ {ep_num - 1}화</a>'
        if prev_url and ep_num > 1
        else f'<span style="color:#bbb">◀ 첫 번째 에피소드</span>'
    )
    next_link = (
        f'<a href="{next_url}" style="color:{accent};text-decoration:none">'
        f'{ep_num + 1}화 ▶</a>'
        if next_url
        else f'<span style="color:#bbb">다음 회 업데이트 예정 ▶</span>'
    )

    # 연재 일정 표기 (예: "매주 월/목 09:00" → "월·목 연재")
    schedule_short = ''
    try:
        m = re.search(r'([가-힣/]+)\s*\d', schedule)
        if m:
            schedule_short = m.group(1).replace('/', '·') + ' 연재'
    except Exception:
        pass

    html = f"""\
<!-- 네이버 블로그 — {title_ko} {ep_num}화 : {title} -->
<div style="max-width:680px;margin:0 auto;padding:16px 0;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#222">

  <!-- 배지 -->
  <div style="margin-bottom:18px">
    <span style="display:inline-block;background:{accent};color:#fff;font-size:12px;font-weight:700;letter-spacing:0.06em;padding:4px 14px;border-radius:20px">
      연재소설 · {ep_num}화
    </span>
  </div>

  <!-- 시리즈 제목 -->
  <p style="margin:0 0 4px 0;font-size:13px;color:#888;font-weight:600;letter-spacing:0.04em">
    {title_ko}
  </p>

  <!-- 에피소드 제목 -->
  <h2 style="margin:0 0 16px 0;font-size:26px;font-weight:800;line-height:1.35;color:#111">
    {title}
  </h2>

  <!-- 메타 -->
  <p style="margin:0 0 28px 0;font-size:13px;color:#aaa">
    {genre} &nbsp;·&nbsp; {today_str}{(' &nbsp;·&nbsp; ' + schedule_short) if schedule_short else ''}
  </p>

  <!-- 네비게이션 (상단) -->
  <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#f7f7f7;border-radius:8px;margin-bottom:32px">
    {prev_link}
    <span style="font-size:12px;color:#aaa;font-weight:600">{ep_num}화</span>
    {next_link}
  </div>

  <!-- 본문 -->
  <div>
    {body_html}
  </div>

  <!-- 구분선 -->
  <hr style="border:none;border-top:2px solid {accent};margin:36px 0 28px 0;opacity:0.3">

  <!-- 다음 회 예고 박스 -->
  <div style="border-left:4px solid {accent};background:#fafafa;padding:18px 20px;border-radius:0 8px 8px 0;margin-bottom:32px">
    <p style="margin:0 0 6px 0;font-size:12px;font-weight:700;color:{accent};letter-spacing:0.06em;text-transform:uppercase">
      다음 에피소드 예고{(' · ' + schedule_short) if schedule_short else ''}
    </p>
    <p style="margin:0;font-size:15px;line-height:1.7;color:#444">
      {hook if hook else '다음 화를 기대해 주세요.'}
    </p>
  </div>

  <!-- 네비게이션 (하단) -->
  <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#f7f7f7;border-radius:8px;margin-bottom:24px">
    {prev_link}
    <span style="font-size:12px;color:#aaa">목록</span>
    {next_link}
  </div>

  <!-- 시리즈 정보 푸터 -->
  <div style="background:#f2f2f2;border-radius:10px;padding:18px 20px;margin-top:8px">
    <p style="margin:0 0 6px 0;font-size:13px;font-weight:700;color:{accent}">
      {title_ko} 정보
    </p>
    <p style="margin:0 0 4px 0;font-size:12px;color:#888">
      장르: {genre} &nbsp;·&nbsp; 목표 {ep_target}화 완결
    </p>
    <p style="margin:0;font-size:12px;color:#aaa">
      연재 일정: {schedule}
    </p>
  </div>

</div>
"""

    if save_file:
        out_dir = BASE_DIR / 'data' / 'novels' / novel_id / 'episodes'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'ep{ep_num:03d}_naver.html'
        try:
            out_path.write_text(html, encoding='utf-8')
            logger.info(f"네이버 HTML 저장: {out_path}")
        except Exception as e:
            logger.error(f"네이버 HTML 저장 실패: {e}")

    logger.info(f"[{novel_id}] 에피소드 {ep_num} 네이버 HTML 변환 완료")
    return html


# ─── 직접 실행 테스트 ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')

    cfg_path = BASE_DIR / 'config' / 'novels' / 'shadow-protocol.json'
    sample_config = json.loads(cfg_path.read_text(encoding='utf-8'))

    sample_episode = {
        'novel_id': 'shadow-protocol',
        'episode_num': 1,
        'title': '프로토콜 제로',
        'body': (
            '빗소리가 유리창을 두드렸다.\n\n'
            '서진은 모니터를 응시했다. 숫자들이 흘러내렸다.\n\n'
            '"아리아, 이 로그 — 누군가 지웠어."\n\n'
            '아리아의 목소리가 낮게 울렸다. "삭제 흔적이 있습니다. 상위 권한 사용자입니다."'
        ),
        'hook': '서진의 이름이 격리 목록에 올라 있었다.',
        'key_scenes': ['서진이 삭제된 로그를 발견하는 장면'],
        'summary': '서진은 오라클 시스템에서 숨겨진 프로토콜을 발견한다.',
        'generated_at': '2026-04-04T00:00:00+00:00',
    }

    html = convert(sample_episode, sample_config)
    print(f"변환 완료 — HTML {len(html)}자")
