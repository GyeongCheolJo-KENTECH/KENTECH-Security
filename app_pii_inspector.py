# ==============================
# app_pii_inspector.py (Streamlit)
# ==============================
import re
from dataclasses import dataclass
from typing import Callable, List, Optional
import streamlit as st

# ---------- 공통 유틸 ----------
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

# 사업자등록번호 체크섬 (10자리)
def brn_check(num: str) -> bool:
    ds = [int(d) for d in re.sub(r"\D", "", num)]
    if len(ds) != 10:
        return False
    w = [1,3,7,1,3,7,1,3,5]
    s = sum(d*w[i] for i, d in enumerate(ds[:9]))
    s += (ds[8]*5)//10
    check = (10 - (s % 10)) % 10
    return check == ds[9]

# 13자리(또는 6-7) 앞 6이 YYMMDD 형태인지 빠른 판별 (CRN과 RRN 구분)
def looks_like_rrn_ymd(num13: str) -> bool:
    n = re.sub(r"\D", "", num13)
    if len(n) != 13:
        return False
    try:
        mm = int(n[2:4]); dd = int(n[4:6])
    except ValueError:
        return False
    return 1 <= mm <= 12 and 1 <= dd <= 31

# ---------- 패턴들 ----------
# 휴대폰
PAT_MOBILE = re.compile(r"\b(01[016789])[-\s]?\d{3,4}[-\s]?\d{4}\b")
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
# CRN 키워드(선택 강화)
KEYWORD_CRN = re.compile(r"(법인등록번호|법인번호|corporate\s*registration)", re.IGNORECASE)

# ---------- 룰/마스킹 ----------
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
        Rule("전화번호", PAT_MOBILE, mask_fn=mask_mobile, color="#c8e6c9"),
        Rule("주민등록번호", PAT_RRN, mask_fn=mask_rrn, color="#ffecb3"),
        Rule("이메일", PAT_EMAIL, mask_fn=mask_email, color="#bbdefb"),
        Rule("카드번호", PAT_CARD, mask_fn=mask_card, validator=lambda m: luhn_check(m.group(0)), color="#ffcdd2"),
        Rule("여권", PAT_PASSPORT, mask_fn=mask_passport, color="#e1bee7"),
        Rule("운전면허", PAT_DRIVER, mask_fn=mask_driver, color="#d7ccc8"),
        Rule("사업자등록번호", PAT_BRN, mask_fn=mask_brn, validator=lambda m: brn_check(m.group(0)), color="#fff0b3"),
        Rule("법인등록번호", PAT_CRN, mask_fn=mask_crn, validator=lambda m: not looks_like_rrn_ymd(m.group(0)), color="#e0f7fa"),
        Rule("연구과제번호", PAT_PROJECT, mask_fn=mask_project, color="#f0b3ff"),
    ]

# ---------- 검출/표기 ----------
@dataclass
class Span:
    rname: str
    start: int
    end: int

def find_spans(text: str, rules: List[Rule], use_account_near_keyword: bool = True, account_window: int = 50, use_crn_keyword: bool = False) -> List[Span]:
    spans: List[Span] = []
    for r in rules:
        for m in r.pattern.finditer(text):
            if r.validator and not r.validator(m):
                continue
            s, e = m.span()
            spans.append(Span(r.name, s, e))

    # 계좌: 키워드 뒤 window에서만
    if use_account_near_keyword:
        for km in KEYWORD_ACCT.finditer(text):
            ks, ke = km.span()
            wend = min(len(text), ke + account_window)
            for am in PAT_ACCT_NUM.finditer(text, ke, wend):
                spans.append(Span("계좌(키워드근접)", am.start(), am.end()))

    # (선택) 법인등록번호 키워드 근접 강화
    if use_crn_keyword:
        for km in KEYWORD_CRN.finditer(text):
            ks, ke = km.span()
            wend = min(len(text), ke + 50)
            for cm in PAT_CRN.finditer(text, ke, wend):
                if looks_like_rrn_ymd(cm.group(0)):
                    continue
                spans.append(Span("법인등록번호(CRN)", cm.start(), cm.end()))

    # 겹침 제거
    spans.sort(key=lambda x: (x.start, x.end))
    filtered: List[Span] = []
    last = -1
    for sp in spans:
        if sp.start >= last:
            filtered.append(sp)
            last = sp.end
    return filtered

# HTML 표기
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
        html.append(f'<mark style="background:{color};padding:0 .2em;border-radius:.2em" title="{label}">{chunk}</mark>')
        i = sp.end
    html.append(escape_html(text[i:]))
    return "".join(html)

# 텍스트 대체
def replace_text(text: str, rules: List[Rule], use_account_near_keyword: bool = True, account_window: int = 50) -> str:
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
                res.append(out[i:]); break
            ks, ke = km.span()
            res.append(out[i:ks]); res.append(out[ks:ke])
            wend = min(len(out), ke + account_window)
            win = out[ke:wend]
            win = PAT_ACCT_NUM.sub(lambda m: f"ACCT[{keep_tail_mask(re.sub(r'\\D','', m.group(0)), 4)}]", win)
            res.append(win)
            i = wend
        out = "".join(res) if res else out

    return out

# ---------- UI ----------
st.set_page_config(page_title="민감정보 표기·대체 도구", layout="wide")
st.title("🔒 민감정보 검출 · 표기(하이라이트) · 대체(마스킹)")

left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("① 입력 & 옵션")
    rules_all = default_rules()

    base_text = st.text_area(
        "여기에 텍스트를 붙여넣으세요",
        key="user_text",
        height=360,
        placeholder="""예) 010-1234-5678, 02-345-6789, name@example.com
220-81-62517(사업자), 110111-1234567(법인), 202300012A(과제)""",
    )

    # 멀티셀렉트 (지방 유선 규칙은 default_rules()에서 제거되어 목록에 없음)
    enabled_names = st.multiselect(
        "적용할 규칙 선택",
        [r.name for r in rules_all],
        default=[r.name for r in rules_all],
    )


with right:
    st.subheader("② 결과")

    # 오른쪽 상단 컨트롤 (출력 모드 + 실행 버튼)
    ctrl_col1, ctrl_col2 = st.columns([3, 1])
    with ctrl_col1:
        mode = st.radio("출력 모드", ["표기(하이라이트)", "대체(마스킹)"], horizontal=True)
    with ctrl_col2:
        run = st.button("🚀 실행", use_container_width=True)


    st.divider()

    if not run:
        st.info("왼쪽에서 텍스트를 입력하고 **실행** 버튼을 누르세요.")
    else:
        if not base_text.strip():
            st.warning("텍스트를 입력하세요.")
        else:
            # 선택한 규칙만 적용
            rules = [r for r in rules_all if r.name in enabled_names]

            # window=50 고정 적용
            spans = find_spans(
                base_text,
                rules,
                use_account_near_keyword=use_account,
                account_window=50,
            )

            # 검출 요약
            if spans:
                counts = {}
                for sp in spans:
                    counts[sp.rname] = counts.get(sp.rname, 0) + 1
                st.write("**검출 요약**")
                st.write(", ".join([f"{k}: {v}건" for k, v in counts.items()]))
            else:
                st.write("검출된 항목 없음")

            # 결과 출력
            if mode == "표기(하이라이트)":
                html = annotate_html(base_text, spans, rules)
                st.markdown(
                    "<div style='white-space:pre-wrap; font-family:ui-monospace, Menlo, Consolas, monospace; line-height:1.6;'>"
                    + html +
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "현재 결과(하이라이트 HTML) 다운로드",
                    html,
                    file_name="annotated.html",
                    mime="text/html",
                    use_container_width=True,
                )
            else:
                redacted = replace_text(
                    base_text,
                    rules,
                    use_account_near_keyword=use_account,
                    account_window=50,  # 고정
                )
                st.text_area("마스킹 결과", value=redacted, height=360)
                st.download_button(
                    "마스킹 결과 TXT 다운로드",
                    redacted,
                    file_name="sanitized.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

# ==================================
# detector.py (검출 전용 JSON 출력)
# ==================================
if False:
    import re, json, argparse
    from dataclasses import dataclass, asdict
    from typing import List, Optional, Callable

    def luhn_check(num: str) -> bool:
        ds = [int(d) for d in re.sub(r"\D", "", num)]
        if len(ds) < 13: return False
        s, alt = 0, False
        for d in reversed(ds):
            v = d * 2 if alt else d
            if alt and v > 9: v -= 9
            s += v; alt = not alt
        return s % 10 == 0

    def brn_check(num: str) -> bool:
        ds = [int(d) for d in re.sub(r"\D", "", num)]
        if len(ds) != 10: return False
        w = [1,3,7,1,3,7,1,3,5]
        s = sum(d*w[i] for i,d in enumerate(ds[:9]))
        s += (ds[8]*5)//10
        check = (10 - (s % 10)) % 10
        return check == ds[9]

    def looks_like_rrn_ymd(num13: str) -> bool:
        n = re.sub(r"\D", "", num13)
        if len(n) != 13: return False
        mm = int(n[2:4]); dd = int(n[4:6])
        return 1 <= mm <= 12 and 1 <= dd <= 31

    PAT = {
        "mobile_phone": re.compile(r"\b(01[016789])[-\s]?\d{3,4}[-\s]?\d{4}\b"),
        "rrn": re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[-]?\d{7}\b"),
        "email": re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"),
        "card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "passport": re.compile(r"\b([MSRHD]\d{8}|[A-Z]{2}\d{7})\b"),
        "driver": re.compile(r"\b\d{2}-\d{2}-\d{6}-\d{2}\b|\b\d{2}-\d{6}-\d{2}\b"),
        "business_reg_no": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{5}\b"),
        "corporate_reg_no": re.compile(r"\b\d{6}[-\s]?\d{7}\b"),
        "project_id": re.compile(r"\b202[0-9]000\d{2}[A-Z]\b"),
    }

    @dataclass
    class Rule:
        name: str; pattern: re.Pattern; validate: Optional[Callable[[re.Match], bool]] = None

    RULES = [
        Rule("mobile_phone", PAT["mobile_phone"]),
        Rule("rrn", PAT["rrn"]),
        Rule("email", PAT["email"]),
        Rule("card", PAT["card"], validate=lambda m: luhn_check(m.group(0))),
        Rule("passport", PAT["passport"]),
        Rule("driver", PAT["driver"]),
        Rule("business_reg_no", PAT["business_reg_no"], validate=lambda m: brn_check(m.group(0))),
        Rule("corporate_reg_no", PAT["corporate_reg_no"], validate=lambda m: not looks_like_rrn_ymd(m.group(0))),
        Rule("project_id", PAT["project_id"]),
    ]

    KEYWORD_ACCT = re.compile(r"(계좌|account|입금|송금|bank)", re.IGNORECASE)
    ACCT_NUMBER = re.compile(r"\b\d{10,14}\b|\b\d{2,6}-\d{2,6}-\d{2,6}\b")
    KEYWORD_CRN = re.compile(r"(법인등록번호|법인번호|corporate\s*registration)", re.IGNORECASE)

    @dataclass
    class Span:
        type: str; start: int; end: int; text: str

    def find_all(text: str) -> List[Span]:
        spans: List[Span] = []
        for r in RULES:
            for m in r.pattern.finditer(text):
                if r.validate and not r.validate(m):
                    continue
                s,e = m.span()
                spans.append(Span(r.name, s, e, text[s:e]))
        # 계좌(키워드 근접)
        for km in KEYWORD_ACCT.finditer(text):
            ks, ke = km.span(); wend = min(len(text), ke+50)
            for am in ACCT_NUMBER.finditer(text, ke, wend):
                spans.append(Span("account", am.start(), am.end(), text[am.start():am.end()]))
        # 겹침 제거
        spans.sort(key=lambda x:(x.start, x.end))
        filtered: List[Span] = []; last=-1
        for sp in spans:
            if sp.start >= last:
                filtered.append(sp); last=sp.end
        return filtered

    def main():
        ap = argparse.ArgumentParser(description="텍스트 내 민감정보 검출(JSON)")
        ap.add_argument("input"); ap.add_argument("--pretty", action="store_true")
        args = ap.parse_args()
        with open(args.input, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        spans = find_all(text)
        out = [asdict(s) for s in spans]
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))

    if __name__ == "__main__":
        main()


# ==================================
# replacer.py (치환 전용 TXT→TXT)
# ==================================
if False:
    import re, argparse

    def luhn_check(num: str) -> bool:
        ds = [int(d) for d in re.sub(r"\D", "", num)]
        if len(ds) < 13: return False
        s, alt = 0, False
        for d in reversed(ds):
            v = d * 2 if alt else d
            if alt and v > 9: v -= 9
            s += v; alt = not alt
        return s % 10 == 0

    def keep_tail_mask(s: str, keep: int = 4, mask_char: str = "*") -> str:
        s2 = re.sub(r"\s", "", s)
        return (mask_char * (len(s2) - keep) + s2[-keep:]) if len(s2) > keep else s

    def brn_check(num: str) -> bool:
        ds = [int(d) for d in re.sub(r"\D", "", num)]
        if len(ds) != 10: return False
        w = [1,3,7,1,3,7,1,3,5]
        s = sum(d*w[i] for i,d in enumerate(ds[:9]))
        s += (ds[8]*5)//10
        check = (10 - (s % 10)) % 10
        return check == ds[9]

    def looks_like_rrn_ymd(num13: str) -> bool:
        n = re.sub(r"\D", "", num13)
        if len(n) != 13: return False
        mm = int(n[2:4]); dd = int(n[4:6])
        return 1 <= mm <= 12 and 1 <= dd <= 31

    # 패턴
    PAT_MOBILE = re.compile(r"\b(01[016789])[-\s]?\d{3,4}[-\s]?\d{4}\b")
    PAT_RRN = re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[-]?\d{7}\b")
    PAT_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
    PAT_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
    PAT_PASSPORT = re.compile(r"\b([MSRHD]\d{8}|[A-Z]{2}\d{7})\b")
    PAT_DRIVER = re.compile(r"\b\d{2}-\d{2}-\d{6}-\d{2}\b|\b\d{2}-\d{6}-\d{2}\b")
    PAT_BRN = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{5}\b")
    PAT_CRN = re.compile(r"\b\d{6}[-\s]?\d{7}\b")
    PAT_PROJECT = re.compile(r"\b202[0-9]000\d{2}[A-Z]\b")

    KEYWORD_ACCT = re.compile(r"(계좌|account|입금|송금|bank)", re.IGNORECASE)
    ACCT_NUMBER = re.compile(r"\b\d{10,14}\b|\b\d{2,6}-\d{2,6}-\d{2,6}\b")

    # 마스킹 함수
    def mask_mobile(m: re.Match) -> str:
        tail2 = re.sub(r"\D", "", m.group(0))[-2:]
        return f"TEL[***-****-**{tail2}]"
    def mask_rrn(m: re.Match) -> str:
        return f"RRN[******-***{m.group(0)[-4:]}]"
    def mask_email(m: re.Match) -> str:
        local, domain = m.group(1), m.group(2)
        masked_local = (local[0] + "*"*(len(local)-1)) if len(local) > 1 else "*"
        return f"EMAIL[{masked_local}@{domain}]"
    def mask_card(m: re.Match) -> str:
        return (f"CARD[**** **** **** {re.sub(r'\\D','',m.group(0))[-4:]}]" if luhn_check(m.group(0)) else m.group(0))
    def mask_passport(m: re.Match) -> str:
        return f"PP[{keep_tail_mask(m.group(0),3)}]"
    def mask_driver(m: re.Match) -> str:
        return f"DL[{keep_tail_mask(re.sub(r'\\D','',m.group(0)),2)}]"
    def mask_brn(m: re.Match) -> str:
        return f"BRN[***-**-**{re.sub(r'\\D','', m.group(0))[-3:]}]"
    def mask_crn(m: re.Match) -> str:
        raw = re.sub(r"\D", "", m.group(0))
        return f"CRN[******-****{raw[-3:]}]"
    def mask_project(m: re.Match) -> str:
        raw = m.group(0)
        return f"PRJ[{raw[:7]}***]"

    RULES = [
        (PAT_MOBILE,  mask_mobile,  None),
        (PAT_RRN,     mask_rrn,     None),
        (PAT_EMAIL,   mask_email,   None),
        (PAT_CARD,    mask_card,    lambda m: luhn_check(m.group(0))),
        (PAT_PASSPORT,mask_passport,None),
        (PAT_DRIVER,  mask_driver,  None),
        (PAT_BRN,     mask_brn,     lambda m: brn_check(m.group(0))),
        (PAT_CRN,     mask_crn,     lambda m: not looks_like_rrn_ymd(m.group(0))),
        (PAT_PROJECT, mask_project, None),
    ]

    def replace_all(text: str) -> str:
        out = text
        for pat, fn, validator in RULES:
            def repl(m):
                return fn(m) if (validator is None or validator(m)) else m.group(0)
            out = pat.sub(repl, out)
        # 계좌(키워드 근접)
        res, i = [], 0
        while i < len(out):
            km = KEYWORD_ACCT.search(out, i, min(len(out), i+800))
            if not km:
                res.append(out[i:]); break
            ks, ke = km.span(); res.append(out[i:ks]); res.append(out[ks:ke])
            wend = min(len(out), ke+50)
            win = out[ke:wend]
            win = ACCT_NUMBER.sub(lambda m: f"ACCT[{keep_tail_mask(re.sub(r'\\D','',m.group(0)),4)}]", win)
            res.append(win); i = wend
        return "".join(res) if res else out

    def main():
        ap = argparse.ArgumentParser(description="텍스트 내 민감정보 대체")
        ap.add_argument("input"); ap.add_argument("-o","--output")
        args = ap.parse_args()
        with open(args.input, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        out = replace_all(text)
        path = args.output or args.input + ".sanitized.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[OK] 저장: {path}")

    if __name__ == "__main__":
        main()










