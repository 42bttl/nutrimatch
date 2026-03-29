"""
케어브릿지헬스 명함 PDF 생성기  (fpdf2 기반)
90mm × 50mm · 1페이지=앞면, 2페이지=뒷면
"""

import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ── 경로 ──────────────────────────────────────────────
BASE   = os.path.dirname(os.path.abspath(__file__))
F_REG  = os.path.join(BASE, 'NotoSansKR-Regular.ttf')
F_BOLD = os.path.join(BASE, 'NotoSansKR-Bold.ttf')

# ── 색상 (R, G, B 0-255) ──────────────────────────────
NAVY    = (11,  43,  74)
NAVY2   = (13,  61,  99)
TEAL    = (10, 138, 122)
TEAL_LT = (13, 184, 158)
GOLD    = (200, 151, 58)
WHITE   = (255, 255, 255)
GRAY    = (138, 155, 173)
GRAY_LT = (176, 196, 208)
DARKBG  = (16,  74, 114)   # 앞면 그라디언트 끝


def lerp(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def h_gradient(pdf, x, y, w, h, c1, c2, steps=80):
    """수평 그라디언트 (왼→오)"""
    pdf.set_line_width(0)
    sw = w / steps + 0.3
    for i in range(steps):
        pdf.set_fill_color(*lerp(c1, c2, i / steps))
        pdf.rect(x + w * i / steps, y, sw, h, style='F')


def v_gradient(pdf, x, y, w, h, c_top, c_bot, steps=80):
    """수직 그라디언트 (위→아래)"""
    pdf.set_line_width(0)
    sh = h / steps + 0.3
    for i in range(steps):
        pdf.set_fill_color(*lerp(c_top, c_bot, i / steps))
        pdf.rect(x, y + h * i / steps, w, sh, style='F')


def tri_h_gradient(pdf, x, y, w, h, c1, c2, c3, split=0.5, steps=100):
    """3색 수평 그라디언트"""
    pdf.set_line_width(0)
    sw = w / steps + 0.3
    for i in range(steps):
        t = i / steps
        if t <= split:
            c = lerp(c1, c2, t / split)
        else:
            c = lerp(c2, c3, (t - split) / (1 - split))
        pdf.set_fill_color(*c)
        pdf.rect(x + w * i / steps, y, sw, h, style='F')


def fill_rect(pdf, x, y, w, h, color, alpha=None):
    pdf.set_fill_color(*color)
    pdf.rect(x, y, w, h, style='F')


def draw_line(pdf, x1, y1, x2, y2, color, lw=0.5):
    pdf.set_draw_color(*color)
    pdf.set_line_width(lw)
    pdf.line(x1, y1, x2, y2)


def draw_text(pdf, text, x, y, font, size, color, align='L'):
    pdf.set_font(font, style='', size=size)
    pdf.set_text_color(*color)
    if align == 'C':
        # fpdf2: use multi_cell or set x
        tw = pdf.get_string_width(text)
        pdf.set_xy(x - tw / 2, y)
    elif align == 'R':
        tw = pdf.get_string_width(text)
        pdf.set_xy(x - tw, y)
    else:
        pdf.set_xy(x, y)
    pdf.cell(0, 0, text)


def text_width(pdf, text, font, size):
    pdf.set_font(font, size=size)
    return pdf.get_string_width(text)


# ── 교량 아이콘 그리기 ──────────────────────────────────
def draw_bridge(pdf, ix, iy, size, navy_color, teal_color, teal_lt_color):
    """
    ix, iy: 아이콘 좌상단 기준
    size: 아이콘 폭 (정사각형)
    """
    tw  = size * 0.18   # 타워 폭
    th  = size * 0.55   # 타워 높이
    deck_y = iy + size * 0.78   # 상판 Y
    deck_h = size * 0.12
    tl_x = ix + size * 0.14    # 왼 타워 X
    tr_x = ix + size * 0.68    # 오른 타워 X
    tower_top_l = deck_y - th
    tower_top_r = deck_y - th

    # 상판
    pdf.set_fill_color(*navy_color)
    pdf.rect(ix, deck_y, size, deck_h, style='F')

    # 타워
    pdf.set_fill_color(*navy_color)
    pdf.rect(tl_x, tower_top_l, tw, th, style='F')
    pdf.rect(tr_x, tower_top_r, tw, th, style='F')

    # 케이블 (왼 타워)
    tcx_l = tl_x + tw / 2
    draw_line(pdf, tcx_l, tower_top_l,      ix - size*0.02, deck_y, teal_color, lw=size*0.04)
    draw_line(pdf, tcx_l, tower_top_l+size*0.08, tl_x + size*0.22, deck_y, teal_color, lw=size*0.04)

    # 케이블 (오른 타워)
    tcx_r = tr_x + tw / 2
    draw_line(pdf, tcx_r, tower_top_r,      ix + size*1.02, deck_y, teal_color, lw=size*0.04)
    draw_line(pdf, tcx_r, tower_top_r+size*0.08, tr_x - size*0.22, deck_y, teal_color, lw=size*0.04)

    # 하트 (교량 중앙 위)
    hcx = (tl_x + tr_x) / 2 + tw / 2
    hcy = tower_top_l - size * 0.12
    hr  = size * 0.14
    draw_heart(pdf, hcx, hcy, hr, teal_lt_color)


def draw_heart(pdf, cx, cy, r, color):
    """간단한 하트: 두 원 + 삼각형 하단"""
    pdf.set_fill_color(*color)
    # 왼쪽 원
    pdf.circle(cx - r*0.5, cy, r*0.6, style='F')
    # 오른쪽 원
    pdf.circle(cx + r*0.5, cy, r*0.6, style='F')
    # 아래 삼각형
    with pdf.local_context():
        pdf.set_fill_color(*color)
        pdf.rect(cx - r, cy, r*2, r*0.8, style='F')  # 중간 채우기
    # 아래 꼭짓점 삼각형
    # fpdf2는 polygon 지원
    try:
        pdf.polygon([
            (cx - r*1.0, cy + r*0.4),
            (cx + r*1.0, cy + r*0.4),
            (cx,         cy + r*1.4),
        ], style='F')
    except Exception:
        pass  # fallback: 삼각형 없이


# ══════════════════════════════════════════════════════
# 옵션 A — 앞면
# ══════════════════════════════════════════════════════
def page_a_front(pdf):
    W, H = 90, 50

    # 배경 그라디언트 (네이비, 위→아래)
    v_gradient(pdf, 0, 0, W, H, DARKBG, NAVY)

    # 장식 원 (우하단)
    with pdf.local_context():
        pdf.set_draw_color(13, 184, 158)
        pdf.set_line_width(0.3)
        pdf.circle(W - 10, H + 5, 12, style='D')
        pdf.set_draw_color(200, 151, 58)
        pdf.set_line_width(0.25)
        pdf.circle(W - 6,  H + 2,  8, style='D')
        pdf.circle(W - 2,  H - 2,  4, style='D')

    # 상단 컬러 바
    tri_h_gradient(pdf, 0, 0, W, 1.8, TEAL, TEAL_LT, GOLD)

    # ── 로고 ──
    lx, ly = 7.5, 8.5
    pdf.set_font('NotoKR-Bold', size=5)
    care_w = pdf.get_string_width('케어')
    pdf.set_text_color(*TEAL_LT)
    pdf.set_xy(lx, ly)
    pdf.cell(care_w, 0, '케어')
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 0, '브릿지헬스')

    pdf.set_font('NotoKR', size=2)
    pdf.set_text_color(200, 200, 200)
    pdf.set_xy(lx, ly + 3.5)
    pdf.cell(0, 0, 'C A R E B R I D G E   H E A L T H')

    # ── 이름 ──
    ny = 22
    pdf.set_font('NotoKR-Bold', size=5.8)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(lx, ny)
    pdf.cell(0, 0, '심영은')

    pdf.set_font('NotoKR', size=2.4)
    pdf.set_text_color(180, 195, 210)
    pdf.set_xy(lx, ny + 4.5)
    pdf.cell(0, 0, 'Youngeun Sim')

    pdf.set_font('NotoKR-Bold', size=2.6)
    pdf.set_text_color(*TEAL_LT)
    pdf.set_xy(lx, ny + 8.5)
    pdf.cell(0, 0, '대표이사  /  CEO')

    # ── 연락처 ──
    cy_c = H - 11
    pdf.set_font('NotoKR', size=2.3)
    pdf.set_text_color(200, 215, 225)
    pdf.set_xy(lx, cy_c)
    pdf.cell(0, 0, 'T.  010-9870-0831')
    pdf.set_xy(lx, cy_c + 4)
    pdf.cell(0, 0, 'E.  2015sim@naver.com')


# ══════════════════════════════════════════════════════
# 옵션 A — 뒷면
# ══════════════════════════════════════════════════════
def page_a_back(pdf):
    W, H = 90, 50

    # 배경 그라디언트 (티얼)
    v_gradient(pdf, 0, 0, W, H, TEAL_LT, TEAL)

    # 장식 원
    with pdf.local_context():
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(0.3)
        pdf.circle(W + 8, -6, 12, style='D')
        pdf.circle(-5, H + 6, 10, style='D')

    cx = W / 2

    # 회사명 (상단)
    pdf.set_font('NotoKR-Bold', size=3.5)
    pdf.set_text_color(*WHITE)
    w1 = pdf.get_string_width('케어브릿지헬스')
    pdf.set_font('NotoKR', size=3.5)
    w2 = pdf.get_string_width(' / CareBridge Health')
    tx = cx - (w1 + w2) / 2
    pdf.set_font('NotoKR-Bold', size=3.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(tx, 7)
    pdf.cell(w1, 0, '케어브릿지헬스')
    pdf.set_font('NotoKR', size=3.5)
    pdf.set_text_color(220, 245, 242)
    pdf.cell(0, 0, ' / CareBridge Health')

    # 슬로건
    pdf.set_font('NotoKR-Bold', size=5)
    pdf.set_text_color(*WHITE)
    sw = pdf.get_string_width('건강을 잇다, 삶을 바꾸다')
    pdf.set_xy(cx - sw/2, H/2 - 3.5)
    pdf.cell(0, 0, '건강을 잇다, 삶을 바꾸다')

    pdf.set_font('NotoKR', size=2.3)
    pdf.set_text_color(215, 240, 237)
    ew = pdf.get_string_width('Bridging Health  ·  Changing Lives')
    pdf.set_xy(cx - ew/2, H/2 + 4)
    pdf.cell(0, 0, 'Bridging Health  ·  Changing Lives')

    # 연락처
    pdf.set_font('NotoKR', size=2)
    pdf.set_text_color(200, 235, 232)
    info = '2015sim@naver.com    |    010-9870-0831'
    iw = pdf.get_string_width(info)
    pdf.set_xy(cx - iw/2, H - 9)
    pdf.cell(0, 0, info)


# ══════════════════════════════════════════════════════
# 옵션 B — 앞면
# ══════════════════════════════════════════════════════
def page_b_front(pdf):
    W, H = 90, 50

    # 흰 배경
    fill_rect(pdf, 0, 0, W, H, WHITE)

    # 왼쪽 사이드바 (네이비)
    v_gradient(pdf, 0, 0, 11, H, NAVY, NAVY2)
    # 하단 티얼 액센트
    fill_rect(pdf, 0, H - 8, 11, 8, TEAL)

    # ── 교량 아이콘 + 텍스트 로고 ──
    icon_size = 8.5
    ix, iy = 14, 5.5
    draw_bridge(pdf, ix, iy, icon_size, NAVY, TEAL, TEAL_LT)

    # 텍스트 로고
    lx = ix + icon_size + 2.5
    ly = iy + 1.2
    pdf.set_font('NotoKR-Bold', size=4)
    care_w = pdf.get_string_width('케어')
    pdf.set_text_color(*TEAL)
    pdf.set_xy(lx, ly)
    pdf.cell(care_w, 0, '케어')
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 0, '브릿지헬스')
    pdf.set_font('NotoKR', size=1.9)
    pdf.set_text_color(*GRAY_LT)
    pdf.set_xy(lx, ly + 3.5)
    pdf.cell(0, 0, 'CareBridge Health')

    # ── 이름 ──
    nx, ny = 14, 21.5
    pdf.set_font('NotoKR-Bold', size=5.8)
    pdf.set_text_color(*NAVY)
    pdf.set_xy(nx, ny)
    pdf.cell(0, 0, '심영은')

    pdf.set_font('NotoKR', size=2.3)
    pdf.set_text_color(*GRAY)
    pdf.set_xy(nx, ny + 4.5)
    pdf.cell(0, 0, 'Youngeun Sim')

    # 직함 배지
    badge = '대표이사 / CEO'
    pdf.set_font('NotoKR-Bold', size=2.4)
    bw = pdf.get_string_width(badge) + 4
    bx, by = nx, ny + 8.5
    fill_rect(pdf, bx, by, bw, 3.8, TEAL)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(bx + 2, by + 0.9)
    pdf.cell(0, 0, badge)

    # ── 연락처 ──
    cy_c = H - 11
    # 작은 원 아이콘
    with pdf.local_context():
        pdf.set_fill_color(*TEAL)
        pdf.circle(nx + 1.5, cy_c + 1, 1.3, style='F')
        pdf.set_fill_color(*TEAL)
        pdf.circle(nx + 1.5, cy_c + 5, 1.3, style='F')

    pdf.set_font('NotoKR', size=2.2)
    pdf.set_text_color(74, 93, 110)
    pdf.set_xy(nx + 4.5, cy_c)
    pdf.cell(0, 0, '010-9870-0831')
    pdf.set_xy(nx + 4.5, cy_c + 4)
    pdf.cell(0, 0, '2015sim@naver.com')


# ══════════════════════════════════════════════════════
# 옵션 B — 뒷면
# ══════════════════════════════════════════════════════
def page_b_back(pdf):
    W, H = 90, 50

    # 흰 배경
    fill_rect(pdf, 0, 0, W, H, WHITE)

    # 상단 스트라이프
    tri_h_gradient(pdf, 0, 0, W, 2, NAVY, TEAL, GOLD, split=0.55)
    # 하단 스트라이프
    h_gradient(pdf, 0, H - 1, W, 1, GOLD, TEAL)

    cx = W / 2

    # 교량 아이콘 (중앙 상단)
    icon_size = 10
    ix = cx - icon_size / 2
    iy = 5
    draw_bridge(pdf, ix, iy, icon_size, NAVY, TEAL, TEAL_LT)

    # 슬로건
    pdf.set_font('NotoKR-Bold', size=5.5)
    pdf.set_text_color(*TEAL)
    s1 = '건강을 잇다,'
    s2 = '삶을 바꾸다'
    w1 = pdf.get_string_width(s1)
    pdf.set_xy(cx - w1/2, H/2 - 2)
    pdf.cell(0, 0, s1)

    pdf.set_font('NotoKR-Bold', size=5.5)
    pdf.set_text_color(*NAVY)
    w2 = pdf.get_string_width(s2)
    pdf.set_xy(cx - w2/2, H/2 + 5)
    pdf.cell(0, 0, s2)

    pdf.set_font('NotoKR', size=2.2)
    pdf.set_text_color(*GRAY)
    en = 'Bridging Health  ·  Changing Lives'
    ew = pdf.get_string_width(en)
    pdf.set_xy(cx - ew/2, H/2 + 12)
    pdf.cell(0, 0, en)

    # 연락처
    pdf.set_font('NotoKR', size=2)
    pdf.set_text_color(*GRAY_LT)
    info = '2015sim@naver.com    ·    010-9870-0831'
    iw = pdf.get_string_width(info)
    pdf.set_xy(cx - iw/2, H - 8)
    pdf.cell(0, 0, info)


# ══════════════════════════════════════════════════════
# 생성 함수
# ══════════════════════════════════════════════════════
def make_pdf(out_name, page1_func, page2_func):
    pdf = FPDF(unit='mm', format=(90, 50))
    pdf.add_font('NotoKR',      style='',  fname=F_REG)
    pdf.add_font('NotoKR-Bold', style='',  fname=F_BOLD)
    pdf.set_auto_page_break(False)

    # 페이지 1: 앞면
    pdf.add_page()
    page1_func(pdf)

    # 페이지 2: 뒷면
    pdf.add_page()
    page2_func(pdf)

    out = os.path.join(BASE, out_name)
    pdf.output(out)
    print(f'✔  {out_name}  ({os.path.getsize(out)//1024} KB, 2페이지)')


if __name__ == '__main__':
    make_pdf('card_A.pdf', page_a_front, page_a_back)
    make_pdf('card_B.pdf', page_b_front, page_b_back)
