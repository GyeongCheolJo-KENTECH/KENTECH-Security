#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit 앱 (계좌 window=50 고정, 슬라이더 제거, 실행 버튼 추가)
- 입력은 폼(form)으로 받고, "실행" 버튼을 눌러야만 결과가 갱신됩니다.
- 계좌 키워드 근접 window는 50으로 고정됩니다.
- 이전에 합의한 패턴(휴대폰/유선/주민/이메일/카드/여권/면허/사업자/법인/과제번호) 모두 포함.
"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional
import streamlit as st

############################################
# 고정 상수
############################################
ACCOUNT_WINDOW = 50  # 계좌 키워드 근접 검색 범위(문자 수) 고정

############################################
# 유틸 함수들
############################################

def luhn_check(num: str) -> bool:
    ds = [int(d) for d in re.sub(r"\D", "", num)]
    if len(ds) < 13:
        return False
    s, alt = 0, False
    for d in reversed(ds):
        v = d * 2 if alt else d
        if alt and v > 9:
            v -= 9
        s += v
        alt = not alt
    return s % 10 == 0


def keep_tail_mask(s: str, keep: int = 4, mask_char: str = "*") -> str:
    s2 = re.sub(r"\s", "", s)
    return (mask_char * (len(s2) - keep) + s2[-keep:]) if len(s2) > keep else s


# 사업자등록번호 체크섬(10자리)
def brn_check(num: str) -> bool:
    ds = [int(d) for d in re.sub(r"\D", "", num)]
    if len(ds) != 10:
        return False
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    s = sum(d * w[i] for i, d in enumerate(ds[:9]))
    s += (ds[8] * 5) // 10
    check = (10 - (s % 10)) % 10
    return check == ds[9]


# 13자리(또는 6-7) 앞 6이 YYMMDD 형태인지 빠른 판별 (CRN과 RRN 구분)
def looks_like_rrn_ymd(num13: str) -> bool:
    n = re.sub(r"\D", "", num13)
    if len(n) != 13:
        return False
    try:
        mm = int(n[2:4])
        dd = int(n[4:6])
    except ValueError:
        return False
    return 1 <= mm <= 12 and 1 <= dd <= 31


############################################
# 패턴들
############################################
# 휴대폰
PAT_MOBILE = re.compile(r"\b(01[016789])[-\s]?\d{3,4}[-\s]?\d{4}\b")
# 유선(서울)
PAT_LAND_SEOUL = re.compile(r"\b(02)[-\s]?\d{3,4}[-\s]?\d{4}\b")
# 유선(지방)
PAT_LAND_OTHERS = re.compile(r"\b(0(?:3[1-3]|4[1-4]|5[1-5]|6[1-4]))[-\s]?\d{3,4}[-\s]?\d{4}\b")
# 주민등록번호(형식)
PAT_RRN = re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[-]?\d{7}\b")
# 이메일
PAT_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# 카드번호(룬검증)
PAT_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# 여권(대한민국 일반형 포함)
PAT_PASSPORT = re.compile(r"\b([MSRHD]\d{8}|[A-Z]{2}\d{7})\b")
# 운전면허(국내 형식)
PAT_DRIVER = re.compile(r"\b\d{2}-\d{2}-\d{6}-\d{2}\b|\b\d{2}-\d{6}-\d{2}\b")
# 계좌 키워드/번호
KEYWORD_ACCT = re.compile(r"(계좌|account|입금|송금|bank)", re.IGNORECASE)
PAT_ACCT_NUM = re.compile(r"\b\d{10,14}\b|\b\d{2,6}-\d{2,6}-\d{2,6}\b")
# 사업자등록번호 10자리
PAT_BRN = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{5}\b")
# 법인등록번호 13자리(형식), RRN처럼 보이면 제외
PAT_CRN = re.compile(r"\b\d{6}[-\s]?\d{7}\b")
# 연구과제번호: 202[0-9]000\d{2}[A-Z]
PAT_PROJECT = re.compile(r"\b202[0-9]000\d{2}[A-Z]\b")
# CRN 키워드(선택 강화. 본 앱에선 기본 미사용)
KEYWORD_CRN = re.compile(r"(법인등록번호|법인번호|corporate\s*registration)", re.IGNORECASE)


############################################
# 룰/마스킹
############################################
@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    mask_fn: Optional[Callable[[re.Match], str]] = None
    validator: Optional[Callable[[re.Match], bool]] = None
    color: str = "#ffd54f"


def mask_mobile(m: re.Match) -> str:
    tail2 = re.sub(r"\D", "", m.group(0))[-2:]
    return f"TEL[***-****-**{tail2}]"


def mask_landline(m: re.Match) -> str:
    area = m.group(1)
    tail2 = re.sub(r"\D", "", m.group(0))[-2:]
    return f"TEL[{area}-***-**{tail2}]"


def mask_rrn(m: re.Match) -> str:
    raw = m.group(0)
    return f"RRN[******-***{raw[-4:]}]"


def mask_email(m: re.Match) -> str:
    local, domain = m.group(1), m.group(2)
    masked_local = (local[0] + "*" * (len(local) - 1)) if len(local) > 1 else "*"
    return f"EMAIL[{masked_local}@{domain}]"


def mask_card(m: re.Match) -> str:
    raw = m.group(0)
    if not luhn_check(raw):
        return raw
    last4 = re.sub(r"\D", "", raw)[-4:]
    return f"CARD[**** **** **** {last4}]"


def mask_passport(m: re.Match) -> str:
    raw = m.group(0)
    return f"PP[{keep_tail_mask(raw, 3)}]"


def mask_driver(m: re.Match) -> str:
    raw = m.group(0)
    return f"DL[{keep_tail_mask(re.sub(r'\\D','', raw), 2)}]"


def mask_brn(m: re.Match) -> str:
    return f"BRN[***-**-**{re.sub(r'\\D','', m.group(0))[-3:]}]"


def mask_crn(m: re.Match) -> str:
    raw = re.sub(r"\D", "", m.group(0))
    return f"CRN[******-****{raw[-3:]}]"


def mask_project(m: re.Match) -> str:
    raw = m.group(0)
    return f"PRJ[{raw[:7]}***]"


def default_rules() -> List[Rule]:
    return [
        Rule("휴대폰(모바일)", PAT_MOBILE, mask_fn=mask_mobile, color="#c8e6c9"),
        Rule("유선(서울 02)", PAT_LAND_SEOUL, mask_fn=mask_landline, color="#d0f0fd"),
        Rule("유선(지방 0xx)", PAT_LAND_OTHERS, mask_fn=mask_landline, color="#e6f7ff"),
        Rule("주민등록번호", PAT_RRN, mask_fn=mask_rrn, color="#ffecb3"),
        Rule("이메일", PAT_EMAIL, mask_fn=mask_email, color="#bbdefb"),
        Rule("카드번호(룬검증)", PAT_CARD, mask_fn=mask_card, validator=lambda m: luhn_check(m.group(0)), color="#ffcdd2"),
        Rule("여권", PAT_PASSPORT, mask_fn=mask_passport, color="#e1bee7"),
        Rule("운전면허", PAT_DRIVER, mask_fn=mask_driver, color="#d7ccc8"),
        Rule("사업자등록번호(BRN)", PAT_BRN, mask_fn=mask_brn, validator=lambda m: brn_check(m.group(0)), color="#fff0b3"),
        Rule("법인등록번호(CRN)", PAT_CRN, mask_fn=mask_crn, validator=lambda m: not looks_like_rrn_ymd(m.group(0)), color="#e0f7fa"),
        Rule("연구과제번호(ProjectID)", PAT_PROJECT, mask_fn=mask_project, color="#f0b3ff"),
    ]


############################################
# 검출/표기/치환 로직
############################################
@dataclass
class Span:
    rname: str
    start: int
    end: int


def find_spans(text: str, rules: List[Rule], use_account_near_keyword: bool = True) -> List[Span]:
    spans: List[Span] = []
    for r in rules:
        for m in r.pattern.finditer(text):
            if r.validator and not r.validator(m):
                continue
            s, e = m.span()
            spans.append(Span(r.name, s, e))

    # 계좌: 키워드 뒤 ACCOUNT_WINDOW에서만
    if use_account_near_keyword:
        for km in KEYWORD_ACCT.finditer(text):
            ks, ke = km.span()
            wend = min(len(text), ke + ACCOUNT_WINDOW)
            for am in PAT_ACCT_NUM.finditer(text, ke, wend):
                spans.append(Span("계좌(키워드근접)", am.start(), am.end()))

    # 겹침 제거
    spans.sort(key=lambda x: (x.start, x.end))
    filtered: List[Span] = []
    last = -1
    for sp in spans:
        if sp.start >= last:
            filtered.append(sp)
            last = sp.end
    return filtered


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def annotate_html(text: str, spans: List[Span], rules: List[Rule]) -> str:
    cmap = {r.name: r.color for r in rules}
    cmap["계좌(키워드근접)"] = "#ffe082"
    html, i = [], 0
    for sp in spans:
        html.append(escape_html(text[i:sp.start]))
        label = sp.rname
        color = cmap.get(label, "#ffd54f")
        chunk = escape_html(text[sp.start:sp.end])
        html.append(
            f'<mark style="background:{color};padding:0 .2em;border-radius:.2em" title="{label}">{chunk}</mark>'
        )
        i = sp.end
    html.append(escape_html(text[i:]))
    return "".join(html)


def replace_text(text: str, rules: List[Rule], use_account_near_keyword: bool = True) -> str:
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
        res, i = [], 0
        while i < len(out):
            km = KEYWORD_ACCT.search(out, i, min(len(out), i + 800))
            if not km:
                res.append(out[i:])
                break
            ks, ke = km.span()
            res.append(out[i:ks])
            res.append(out[ks:ke])  # 키워드는 그대로 보존
            wend = min(len(out), ke + ACCOUNT_WINDOW)
            win = out[ke:wend]
            win = PAT_ACCT_NUM.sub(
                lambda m: f"ACCT[{keep_tail_mask(re.sub(r'\\D','', m.group(0)), 4)}]",
                win,
            )
            res.append(win)
            i = wend
        out = "".join(res) if res else out

    return out


############################################
# UI (폼 + 실행 버튼)
############################################
st.set_page_config(page_title="민감정보 표기·대체 도구", layout="wide")
st.title("🔒 민감정보 검출 · 표기(하이라이트) · 대체(마스킹)")
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("① 입력 & 옵션")
    rules_all = default_rules()

    with st.form("pii_form"):
            base_text = st.text_area(
            "여기에 텍스트를 붙여넣으세요",
            height=360,
            placeholder=(
            "예) 010-1234-5678, 02-345-6789, 031-234-5678, name@example.com,\\n"
            "220-81-62517(사업자), 110111-1234567(법인), 202100099A(과제)"
            ),\n)

        # 전화번호 필터 통합: 휴대폰/유선(서울)/유선(지방) 하나의 체크박스로 관리
        phone_names = ["휴대폰(모바일)", "유선(서울 02)", "유선(지방 0xx)"]
        phone_enabled = st.checkbox("전화번호(모바일+유선) 포함", value=True)

        # 나머지 규칙은 멀티셀렉트로 관리 (전화번호 3종은 목록에서 제외)
        rules_all = default_rules()
        other_rules = [r for r in rules_all if r.name not in phone_names]
        enabled_other = st.multiselect(
            "적용할 규칙 선택 (전화번호 제외)",
            [r.name for r in other_rules],
            default=[r.name for r in other_rules],
        )

        # 최종 rules 조립을 위해 세션 상태에 저장
        st.session_state._phone_enabled = phone_enabled
        st.session_state._enabled_other = enabled_other

        use_account = st.checkbox("계좌(키워드 근접) 포함 (window=50 고정)", value=True)
        st.session_state._use_account = use_account



with right:
    mode = st.radio("출력 모드", ["표기(하이라이트)", "대체(마스킹)"], horizontal=True)
    st.session_state._mode = mode

    submitted = st.form_submit_button("🚀 실행")
    st.subheader("② 결과")
    # 폼에서 선택한 옵션 복원
    phone_names = ["휴대폰(모바일)", "유선(서울 02)", "유선(지방 0xx)"]
    rules_all = default_rules()
    other_rules = [r for r in rules_all if r.name not in phone_names]

    if "_enabled_other" in st.session_state and "_phone_enabled" in st.session_state:
        enabled_other = st.session_state._enabled_other
        phone_enabled = st.session_state._phone_enabled
        rules: List[Rule] = [r for r in other_rules if r.name in enabled_other]
        if phone_enabled:
            rules.extend([r for r in rules_all if r.name in phone_names])
    else:
        # 초기값(모두 켜짐)
        rules = rules_all

    use_account = st.session_state.get("_use_account", True)
    mode = st.session_state.get("_mode", "표기(하이라이트)")

    if not st.session_state.get("_mode") or not st.session_state.get("_enabled_other"):
        st.info("왼쪽에서 텍스트와 옵션을 설정한 뒤 **실행** 버튼을 누르세요.")
    else:
        base_text = st.session_state.get("user_text") or ""

    # 실행 버튼 결과 표시
    if 'submitted' in locals() and submitted:
        if not base_text.strip():
            st.warning("텍스트를 입력하세요.")
        else:
            spans = find_spans(base_text, rules, use_account_near_keyword=use_account)
            if spans:
                counts = {}
                for sp in spans:
                    counts[sp.rname] = counts.get(sp.rname, 0) + 1
                st.write("**검출 요약**")
                st.write(", ".join([f"{k}: {v}건" for k, v in counts.items()]))
            else:
                st.write("검출된 항목 없음")

            if mode == "표기(하이라이트)":
                html = annotate_html(base_text, spans, rules)
                st.markdown(
                    f"<div style='white-space:pre-wrap; font-family:ui-monospace, Menlo, Consolas, monospace; line-height:1.6;'>{html}</div>",
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "현재 결과(하이라이트 HTML) 다운로드",
                    html,
                    file_name="annotated.html",
                    mime="text/html",
                )
            else:
                redacted = replace_text(base_text, rules, use_account_near_keyword=use_account)
                st.text_area("대체 결과", value=redacted, height=360)
                st.download_button(
                    "대체 결과 TXT 다운로드", redacted, file_name="sanitized.txt", mime="text/plain"
                )


