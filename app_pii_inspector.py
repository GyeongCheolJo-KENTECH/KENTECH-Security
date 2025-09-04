#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =========================
# 0) 공통 임포트
# =========================
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
import streamlit as st

# =========================
# 1) 텍스트 읽기 파트 (Input Reader)
# =========================
def read_text_from_ui() -> str:
    """
    왼쪽(좌측 컬럼)에 텍스트 입력 또는 파일 업로드를 통해 원문 텍스트를 확보.
    파일은 .txt만 처리 (간단 예시). 인코딩은 utf-8 우선, 실패 시 ignore.
    """
    st.sidebar.header("입력 방법")
    src_mode = st.sidebar.radio("Input Source", ["텍스트 직접 입력", "TXT 파일 업로드"], horizontal=True)
    if src_mode == "텍스트 직접 입력":
        text = st.session_state.get("user_text", "")
        return text
    else:
        up = st.sidebar.file_uploader("TXT 업로드", type=["txt"])
        if up is not None:
            try:
                return up.read().decode("utf-8", errors="ignore")
            except Exception:
                return ""
        return ""

# =========================
# 2) 민감정보 설정 파트 (Rules Config)
# =========================
@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    mask_fn: Optional[Callable[[re.Match], str]] = None
    validator: Optional[Callable[[re.Match], bool]] = None
    color: str = "#ffd54f"  # 하이라이트 색 (표기 모드)

def luhn_check(num: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", num)]
    if len(digits) < 13:
        return False
    s = 0
    alt = False
    for d in reversed(digits):
        d2 = d * 2 if alt else d
        if alt and d2 > 9:
            d2 -= 9
        s += d2
        alt = not alt
    return s % 10 == 0

def keep_tail_mask(s: str, keep: int = 4, mask_char: str = "*") -> str:
    s_clean = re.sub(r"\s", "", s)
    if len(s_clean) <= keep:
        return s
    return mask_char * (len(s_clean) - keep) + s_clean[-keep:]

def default_rules() -> List[Rule]:
    """대표 규칙 세트 (체크박스로 On/Off 가능)"""
    # 마스킹 함수들
    def mask_rrn(m: re.Match) -> str:
        raw = m.group(0)
        return f"RRN[******-***{raw[-4:]}]"

    def mask_phone(m: re.Match) -> str:
        raw = m.group(0)
        tail2 = re.sub(r"\D", "", raw)[-2:]
        return f"TEL[***-****-**{tail2}]"

    def mask_email(m: re.Match) -> str:
        local, domain = m.group(1), m.group(2)
        masked_local = (local[0] + "*" * (len(local) - 1)) if len(local) > 1 else "*"
        return f"EMAIL[{masked_local}@{domain}]"

    def mask_card(m: re.Match) -> str:
        raw = m.group(0)
        return f"CARD[**** **** **** {re.sub(r'\\D','',raw)[-4:]}]"

    def mask_passport(m: re.Match) -> str:
        raw = m.group(0)
        return f"PP[{keep_tail_mask(raw, 3)}]"

    def mask_kor_driver(m: re.Match) -> str:
        raw = m.group(0)
        return f"DL[{keep_tail_mask(re.sub(r'\\D','',raw), 2)}]"

    return [
        Rule(
            "주민등록번호",
            re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[-]?\d{7}\b"),
            mask_fn=mask_rrn,
            color="#ffecb3",
        ),
        Rule(
            "전화번호",
            re.compile(r"\b(01[016789]|0\d{1,2})-?\d{3,4}-?\d{4}\b"),
            mask_fn=mask_phone,
            color="#c8e6c9",
        ),
        Rule(
            "이메일",
            re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"),
            mask_fn=mask_email,
            color="#bbdefb",
        ),
        Rule(
            "카드번호(룬검증)",
            re.compile(r"\b(?:\d[ -]?){13,19}\b"),
            mask_fn=mask_card,
            validator=lambda m: luhn_check(m.group(0)),
            color="#ffcdd2",
        ),
        Rule(
            "여권(대한민국 일반형 포함)",
            re.compile(r"\b([MSRHD]\d{8}|[A-Z]{2}\d{7})\b"),
            mask_fn=mask_passport,
            color="#e1bee7",
        ),
        Rule(
            "운전면허(국내 형식)",
            re.compile(r"\b\d{2}-\d{2}-\d{6}-\d{2}\b|\b\d{2}-\d{6}-\d{2}\b"),
            mask_fn=mask_kor_driver,
            color="#d7ccc8",
        ),
    ]

# 계좌: 키워드 근접 탐지/대체 옵션
KEYWORD_ACCT = re.compile(r"(계좌|account|입금|송금|bank)", re.IGNORECASE)
ACCT_NUMBER = re.compile(r"\b\d{10,14}\b|\b\d{2,6}-\d{2,6}-\d{2,6}\b")

# =========================
# 3) 민감정보 검색 파트 (PII Detector)
# =========================
@dataclass
class Span:
    rname: str
    start: int
    end: int

def find_spans(text: str, rules: List[Rule], use_account_near_keyword: bool = True, account_window: int = 50) -> List[Span]:
    spans: List[Span] = []
    for r in rules:
        for m in r.pattern.finditer(text):
            if r.validator and not r.validator(m):
                continue
            s, e = m.span()
            spans.append(Span(r.name, s, e))
    if use_account_near_keyword:
        for km in KEYWORD_ACCT.finditer(text):
            ks, ke = km.span()
            win_end = min(len(text), ke + account_window)
            for am in ACCT_NUMBER.finditer(text, ke, win_end):
                s, e = am.span()
                spans.append(Span("계좌(키워드근접)", s, e))
    # 겹침 제거 (앞쪽 우선)
    spans.sort(key=lambda x: (x.start, x.end))
    filtered = []
    last_end = -1
    for sp in spans:
        if sp.start >= last_end:
            filtered.append(sp)
            last_end = sp.end
    return filtered

# =========================
# 4) 민감정보 표기/대체 파트 (Annotator / Redactor)
# =========================
def annotate_html(text: str, spans: List[Span], rules: List[Rule]) -> str:
    """
    표기 모드: 민감정보를 컬러 하이라이트 HTML로 표시 (우측 출력창)
    """
    # 규칙 색상 매핑
    cmap = {r.name: r.color for r in rules}
    cmap["계좌(키워드근접)"] = "#ffe082"
    # 조각 합치기
    html = []
    i = 0
    for sp in spans:
        html.append(escape_html(text[i:sp.start]))
        label = sp.rname
        color = cmap.get(label, "#ffd54f")
        chunk = escape_html(text[sp.start:sp.end])
        html.append(f'<mark style="background:{color}; padding:0 .2em; border-radius:.2em;" title="{label}">{chunk}</mark>')
        i = sp.end
    html.append(escape_html(text[i:]))
    return "".join(html)

def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )

def replace_text(text: str, rules: List[Rule], use_account_near_keyword: bool = True, account_window: int = 50) -> str:
    """
    대체(마스킹) 모드: 규칙 기반으로 텍스트 자체를 변경
    """
    out = text
    for r in rules:
        if r.mask_fn is None:
            continue
        def repl(m: re.Match) -> str:
            if r.validator and not r.validator(m):
                return m.group(0)
            return r.mask_fn(m)
        out = r.pattern.sub(repl, out)

    if use_account_near_keyword:
        # 키워드 뒤 window 영역만 계좌 마스킹
        result = []
        i = 0
        while i < len(out):
            km = KEYWORD_ACCT.search(out, i, min(len(out), i + 800))
            if not km:
                result.append(out[i:])
                break
            ks, ke = km.span()
            result.append(out[i:ks])
            result.append(out[ks:ke])
            win_end = min(len(out), ke + account_window)
            win = out[ke:win_end]
            def arepl(m: re.Match) -> str:
                raw = re.sub(r"\D", "", m.group(0))
                return f"ACCT[{keep_tail_mask(raw, 4)}]"
            win2 = ACCT_NUMBER.sub(arepl, win)
            result.append(win2)
            i = win_end
        out = "".join(result)

    return out

# =========================
# 5) UI 구성 (왼쪽 입력, 오른쪽 출력)
# =========================
st.set_page_config(page_title="민감정보 표기·대체 도구", layout="wide")

st.title("🔒 민감정보 검출 · 표기(하이라이트) · 대체(마스킹)")

# 좌/우 컬럼
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("① 입력(왼쪽)")
    st.text_area(
        "여기에 텍스트를 붙여넣으세요 (또는 좌측 사이드바에서 파일 업로드)",
        key="user_text",
        height=360,
        placeholder="예) 홍길동 900101-1234567, 010-1234-5678, name@example.com, 카드 4111 1111 1111 1111 ..."
    )

    st.divider()
    st.subheader("② 민감정보 설정")
    rules_all = default_rules()

    enabled_names = st.multiselect(
        "적용할 규칙 선택",
        [r.name for r in rules_all],
        default=[r.name for r in rules_all],
    )
    rules = [r for r in rules_all if r.name in enabled_names]

    use_account = st.checkbox("계좌(키워드 근접) 포함", value=True)
    acct_window = st.slider("계좌 키워드 뒤 검색 범위(문자 수)", min_value=20, max_value=200, value=50, step=5)

    mode = st.radio("출력 모드", ["표기(하이라이트)", "대체(마스킹)"], horizontal=True)

with right:
    st.subheader("③ 결과(오른쪽)")

    # 입력 원문 확보
    base_text = read_text_from_ui()

    # 빈 입력 처리
    if not base_text.strip():
        st.info("왼쪽에 텍스트를 입력하거나 파일을 업로드하세요.")
    else:
        # 검색
        spans = find_spans(base_text, rules, use_account_near_keyword=use_account, account_window=acct_window)

        # 통계
        if spans:
            counts = {}
            for sp in spans:
                counts[sp.rname] = counts.get(sp.rname, 0) + 1
            st.write("**검출 요약**")
            st.write(", ".join([f"{k}: {v}건" for k, v in counts.items()]))
        else:
            st.write("검출된 항목 없음")

        # 출력
        if mode == "표기(하이라이트)":
            html = annotate_html(base_text, spans, rules)
            st.markdown(
                f"""
                <div style="white-space:pre-wrap; font-family:ui-monospace, Menlo, Consolas, monospace; line-height:1.6;">
                    {html}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.download_button("현재 결과(하이라이트 HTML) 다운로드", html, file_name="annotated.html", mime="text/html")
        else:
            redacted = replace_text(base_text, rules, use_account_near_keyword=use_account, account_window=acct_window)
            st.text_area("마스킹 결과", value=redacted, height=360)
            st.download_button("마스킹 결과 TXT 다운로드", redacted, file_name="sanitized.txt", mime="text/plain")

st.caption("※ 카드번호는 룬(Luhn) 검증을 통과하는 경우에만 대체합니다. 계좌는 키워드(계좌/입금/송금/bank) 인접 구간에서만 대체합니다.")