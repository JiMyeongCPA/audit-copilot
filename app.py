import html
import os

import altair as alt
import pandas as pd
import streamlit as st
from google.genai import errors as genai_errors
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode

from industry_analysis import (
    compute_boxplot_stats,
    compute_company_ratios,
    compute_growth_boxplot_stats,
    compute_industry_average,
    load_database,
)
from audit_question_generator import generate_audit_questions
from chat_assistant import generate_chat_reply

st.set_page_config(
    page_title="Audit Copilot", layout="wide", page_icon="🔍", initial_sidebar_state="collapsed"
)

CONTRACT_ASSET_NOTE = (
    "계약자산(미청구공사)은 진행기준으로 인식한 수익 중 아직 청구되지 않은 금액으로, "
    "매출채권과 달리 청구권이 확정되지 않았습니다. 공사 진행률 및 수익 인식의 적정성에 따라 "
    "금액이 달라질 수 있으므로 참고하시기 바랍니다."
)

# 계정 클릭 시 보여줄 비율들 (첫 번째 항목이 추이차트/박스플롯에 쓰이는 대표 비율).
# pct=True면 %로, suffix가 있으면 그 단위로, 그 외엔 배수(예: 3.45회)로 표시.
RATIO_FAMILIES = {
    "매출채권": [
        {"col": "매출채권회전율", "label": "매출채권회전율", "pct": False,
         "desc": "매출액을 매출채권으로 나눈 값. 낮을수록 채권 회수가 느리다는 뜻으로, 회수불능·매출 과대계상 위험을 볼 때 씁니다."},
        {"col": "매출채권평균회수기간", "label": "매출채권평균회수기간(DSO)", "pct": False, "suffix": "일",
         "desc": "매출채권을 현금으로 회수하는 데 평균 며칠 걸리는지. 길어지면 회수 지연이나 대손 위험이 커졌을 수 있습니다."},
        {"col": "매출채권매출액비율", "label": "매출채권/매출액", "pct": True,
         "desc": "매출 대비 아직 못 받은 채권이 얼마나 쌓여있는지. 갑자기 늘면 매출을 부풀렸거나 회수가 안 되고 있다는 신호일 수 있습니다."},
    ],
    "재고자산": [
        {"col": "재고자산회전율", "label": "재고자산회전율", "pct": False,
         "desc": "매출원가를 재고자산으로 나눈 값. 낮을수록 재고가 안 팔리고 쌓여있다는 뜻으로, 진부화·평가손실 위험을 볼 때 씁니다."},
        {"col": "재고자산매출액비율", "label": "재고자산/매출액", "pct": True,
         "desc": "매출 대비 재고가 얼마나 쌓여있는지. 비율이 갑자기 커지면 판매 부진이나 재고 누적을 의심해볼 수 있습니다."},
    ],
    "계약자산": [
        {"col": "계약자산매출액비율", "label": "계약자산/매출액", "pct": True,
         "desc": "매출 중 아직 청구하지 않은(진행기준으로만 인식한) 금액의 비중. 크면 수익 조기인식 위험을 볼 때 씁니다."},
        {"col": "계약자산매출채권비율", "label": "계약자산/매출채권", "pct": True,
         "desc": "청구권이 확정된 매출채권 대비, 아직 청구 전인 계약자산이 얼마나 큰지 — 비중이 높으면 회수 불확실성이 상대적으로 큽니다."},
    ],
    "현금및현금성자산": [
        {"col": "현금비율", "label": "현금비율", "pct": True,
         "desc": "유동부채 대비 즉시 현금화 가능한 자산 비중. 가장 보수적인 단기 지급능력 지표입니다."},
    ],
    "유동자산": [
        {"col": "유동비율", "label": "유동비율", "pct": True,
         "desc": "유동부채 대비 유동자산 비율. 100% 밑이면 1년 내 갚을 돈보다 1년 내 현금화할 자산이 적다는 뜻(단기 유동성 위험)."},
        {"col": "당좌비율", "label": "당좌비율", "pct": True,
         "desc": "유동비율에서 재고자산(현금화가 더딜 수 있는 자산)을 뺀 값. 유동비율보다 더 보수적인 단기 지급능력 지표입니다."},
    ],
    "매입채무": [
        {"col": "매입채무회전율", "label": "매입채무회전율", "pct": False,
         "desc": "매출원가를 매입채무로 나눈 값. 너무 낮으면(매입채무가 과도하게 크면) 대금 지급 지연이나 자금 압박을 의심해볼 수 있습니다."},
    ],
    "부채총계": [
        {"col": "부채비율", "label": "부채비율", "pct": True,
         "desc": "자본 대비 부채 비율. 100% 넘으면 부채가 자본보다 많다는 뜻으로, 재무안정성·계속기업 위험을 볼 때 기본이 되는 지표입니다."},
        {"col": "총부채총자산", "label": "총부채/총자산", "pct": True,
         "desc": "전체 자산 중 빚으로 조달한 비중. 높을수록 재무레버리지가 크다는 뜻입니다."},
        {"col": "차입금의존도", "label": "차입금의존도", "pct": True,
         "desc": "전체 자산 중 이자를 내야 하는 차입금(단기+유동성장기+장기)의 비중. 높으면 이자 부담·차환 위험이 큽니다."},
    ],
    "장기차입금": [
        {"col": "장기차입금자산비율", "label": "장기차입금/총자산", "pct": True,
         "desc": "총자산 대비 장기차입금 비중. 장기 재무레버리지와 대출 약정(코버넌트) 위반 위험을 볼 때 씁니다."},
    ],
    "자본총계": [
        {"col": "ROE", "label": "ROE", "pct": True,
         "desc": "자기자본이익률 — 주주가 투자한 자본으로 얼마나 이익을 냈는지. 급격한 변동은 이익조정이나 자본 변동(자사주 등)을 의심해볼 신호입니다."},
    ],
    "매출액": [
        {"col": "총자산회전율", "label": "총자산회전율", "pct": False,
         "desc": "매출액을 총자산으로 나눈 값. 자산을 얼마나 효율적으로 굴려 매출을 내는지 보는 지표입니다."},
    ],
    "매출원가": [
        {"col": "매출원가율", "label": "매출원가율", "pct": True,
         "desc": "매출액 대비 매출원가 비중. 갑자기 바뀌면 원가 누락·재고평가·매출총이익률 왜곡을 의심해볼 수 있습니다."},
    ],
    "자산총계": [],
    "영업이익": [
        {"col": "영업이익률", "label": "영업이익률", "pct": True,
         "desc": "매출액 대비 영업이익 비중 — 본업에서 실제로 남긴 이익률입니다."},
        {"col": "이자보상배율", "label": "이자보상배율", "pct": False,
         "desc": "영업이익을 이자비용(금융원가)으로 나눈 값. 1배 미만이면 벌어들인 돈으로 이자도 못 낸다는 뜻 — 계속기업 위험의 핵심 지표입니다."},
    ],
    "당기순이익": [
        {"col": "순이익률", "label": "순이익률", "pct": True,
         "desc": "매출액 대비 최종 순이익 비중. 영업이익률과 차이가 크면 영업외손익(일회성 손익)의 영향이 크다는 뜻입니다."},
        {"col": "ROA", "label": "ROA", "pct": True,
         "desc": "총자산이익률 — 보유한 전체 자산으로 얼마나 이익을 냈는지 보는 지표입니다."},
    ],
    "금융원가": [
        {"col": "금융원가차입금비율", "label": "금융원가/총차입금", "pct": True,
         "desc": "차입금 대비 실제로 부담한 이자비용 비율 — 대략적인 실질 조달금리로, 갑자기 튀면 차입조건 악화나 이자 누락을 의심해볼 수 있습니다."},
    ],
    # 2단계 확장
    "유형자산": [
        {"col": "유형자산회전율", "label": "유형자산회전율", "pct": False,
         "desc": "매출액을 유형자산으로 나눈 값. 낮으면 설비 활용도가 낮거나 유휴자산·손상 징후를 의심해볼 수 있습니다."},
        {"col": "유형자산총자산비율", "label": "유형자산/총자산", "pct": True,
         "desc": "전체 자산 중 유형자산(설비 등) 비중. 자산 구조상 유형자산 의존도와 손상위험을 볼 때 씁니다."},
    ],
    "사용권자산": [
        {"col": "사용권자산총자산비율", "label": "사용권자산/총자산", "pct": True,
         "desc": "전체 자산 중 리스(임차)로 인식한 사용권자산 비중. 높으면 리스 의존도가 크다는 뜻입니다."},
    ],
    "무형자산": [
        {"col": "무형자산총자산비율", "label": "무형자산/총자산", "pct": True,
         "desc": "전체 자산 중 무형자산(개발비·소프트웨어 등) 비중. 높으면 자산화 정책의 적정성과 손상위험을 더 살펴볼 필요가 있습니다."},
    ],
    "영업권": [
        {"col": "영업권총자산비율", "label": "영업권/총자산", "pct": True,
         "desc": "전체 자산 중 영업권(인수·합병으로 생긴 프리미엄) 비중. 높으면 손상검사 중요성이 커집니다."},
    ],
    "투자부동산": [
        {"col": "투자부동산총자산비율", "label": "투자부동산/총자산", "pct": True,
         "desc": "전체 자산 중 투자목적 부동산 비중. 공정가치 평가·임대수익성 관련 위험을 볼 때 씁니다."},
    ],
    "관계기업투자": [
        {"col": "관계기업투자총자산비율", "label": "관계기업투자/총자산", "pct": True,
         "desc": "전체 자산 중 관계기업·공동기업 투자 비중. 지분법 평가나 특수관계자 거래의 중요성을 볼 때 씁니다."},
    ],
    "이연법인세자산": [
        {"col": "이연법인세자산자본비율", "label": "이연법인세자산/자본총계", "pct": True,
         "desc": "자본 대비 이연법인세자산 비중. 크면 미래에 실제로 세금을 아낄 수 있을지(실현가능성) 따져볼 필요가 있습니다."},
    ],
    "유동충당부채": [
        {"col": "충당부채매출액비율", "label": "충당부채/매출액", "pct": True,
         "desc": "매출 대비 충당부채(판매보증·소송·복구의무 등 추정 부채) 비중. 회계추정의 위험도를 볼 때 씁니다."},
    ],
    "계약부채": [
        {"col": "계약부채매출액비율", "label": "계약부채/매출액", "pct": True,
         "desc": "매출 대비 선수금 성격의 계약부채 비중. 수행의무 이행 시점과 수익인식이 적절히 이연되고 있는지 볼 때 씁니다."},
    ],
    "자본금": [],
    "이익잉여금": [],
    "자기주식": [
        {"col": "자기주식자본비율", "label": "자기주식/자본총계", "pct": True,
         "desc": "자본 대비 자기주식(자사주) 비중. 자사주 취득·처분 거래의 중요성을 볼 때 씁니다."},
    ],
    "매출총이익": [
        {"col": "매출총이익률", "label": "매출총이익률", "pct": True,
         "desc": "매출액 대비 매출총이익 비중. 가격·원가 구조 변화나 수익성 이상징후를 볼 때 기본이 되는 지표입니다."},
    ],
    "판매비와관리비": [
        {"col": "판관비율", "label": "판관비율", "pct": True,
         "desc": "매출액 대비 판매비와관리비 비중. 비정상적인 비용 절감이나 비용 분류 오류를 의심해볼 때 씁니다."},
    ],
    "금융수익": [
        {"col": "금융수익매출액비율", "label": "금융수익/매출액", "pct": True,
         "desc": "매출 대비 이자수익 등 금융수익 비중. 크면 본업 외 수익 의존도나 일회성 손익 영향을 의심해볼 수 있습니다."},
    ],
    "법인세비용차감전순이익": [
        {"col": "세전이익률", "label": "세전이익률", "pct": True,
         "desc": "매출액 대비 법인세 반영 전 이익 비중. 영업외손익까지 포함한 전체 수익성을 볼 때 씁니다."},
    ],
    "법인세비용": [
        {"col": "유효세율", "label": "유효세율", "pct": True,
         "desc": "세전이익 대비 실제 부담한 법인세 비율. 법정세율과 크게 다르면 이연법인세·세무조정·일회성 세효과를 짚어볼 필요가 있습니다."},
    ],
    # 현금흐름표 확장 (3단계)
    "영업활동현금흐름": [
        {"col": "OCF매출액비율", "label": "OCF/매출액", "pct": True,
         "desc": "영업활동현금흐름을 매출액으로 나눈 값. 당기순이익은 늘었는데 이 비율이 낮거나 줄어들면 이익의 질(수익 조기인식·매출채권 누적 등)을 의심해볼 신호입니다."},
    ],
    "투자활동현금흐름": [
        {"col": "투자현금흐름부담률", "label": "투자현금흐름 부담률", "pct": True,
         "desc": "매출액 대비 투자활동 순현금유출 규모. 높으면 설비·사업 확장에 현금을 많이 쓰고 있다는 뜻이고, 영업현금흐름으로 못 감당하면 외부자금 조달 필요성을 볼 신호입니다."},
    ],
    "재무활동현금흐름": [
        {"col": "외부자금의존도", "label": "외부자금 의존도", "pct": True,
         "desc": "재무활동현금흐름을 영업활동현금흐름으로 나눈 값. 양(+)이 크면 영업으로 번 돈보다 외부 조달(차입·증자)에 의존한다는 뜻입니다."},
    ],
    "유형자산취득액": [
        {"col": "CAPEX커버리지", "label": "CAPEX 커버리지", "pct": False,
         "desc": "영업활동현금흐름을 유형·무형자산 취득액(CAPEX)으로 나눈 값. 1배 미만이면 영업으로 번 현금만으로 설비투자를 못 감당해 외부자금이 필요하다는 뜻입니다."},
    ],
    "무형자산취득액": [],
    "유형자산처분액": [
        {"col": "자산처분현금비율", "label": "자산처분/매출액", "pct": True,
         "desc": "매출액 대비 유형·무형자산 처분으로 들어온 현금 비중. 갑자기 커지면 핵심자산 매각으로 일시적으로 현금흐름을 좋게 보이려 한 건 아닌지 볼 신호입니다."},
    ],
    "무형자산처분액": [],
    "배당금지급액": [
        {"col": "영업현금배당지급률", "label": "영업현금 배당지급률", "pct": True,
         "desc": "영업활동현금흐름 중 배당으로 지급한 비중. 100%에 가깝거나 넘으면 영업현금 대비 배당이 과도해 재무 여력을 갉아먹고 있을 수 있습니다."},
    ],
    "법인세납부액": [
        {"col": "현금세율", "label": "현금세율", "pct": True,
         "desc": "법인세차감전순이익 대비 실제 현금으로 납부한 세금 비율. 손익계산서상 유효세율과 크게 다르면 이연법인세나 세무조정 항목을 짚어볼 필요가 있습니다."},
    ],
    "이자지급액": [
        {"col": "현금이자율", "label": "현금이자율", "pct": True,
         "desc": "평균 차입금 대비 실제 현금으로 지급한 이자 비율. 손익계산서상 금융원가/차입금 비율과 크게 다르면 발생주의-현금주의 괴리(미지급이자 누적 등)를 볼 신호입니다."},
    ],
    "단기차입금유입액": [],
    "장기차입금유입액": [
        {"col": "신규차입률", "label": "신규차입률", "pct": True,
         "desc": "평균 차입금 대비 당기 중 새로 차입한 금액 비율. 높으면 차입 규모를 빠르게 늘리고 있다는 뜻으로, 차입 목적과 상환 계획을 볼 필요가 있습니다."},
    ],
    "단기차입금상환액": [],
    "장기차입금상환액": [
        {"col": "차입금상환률", "label": "차입금상환률", "pct": True,
         "desc": "평균 차입금 대비 당기 중 상환한 금액 비율. 신규차입률과 같이 보면 차입금이 순증가하는 추세인지 축소하는 추세인지 알 수 있습니다."},
    ],
    "리스부채상환액": [
        {"col": "리스부채상환률", "label": "리스부채상환률", "pct": True,
         "desc": "평균 리스부채 대비 당기 중 상환한 금액 비율. 사용권자산 규모와 같이 보면 리스 관련 현금 부담이 적정한지 볼 수 있습니다."},
    ],
    "유동리스부채": [],
    "비유동리스부채": [],
}

CLICKABLE_ACCOUNTS = list(RATIO_FAMILIES.keys())

# 재무상태표: 자산 계정들 -> 자산총계 -> 부채 계정들 -> 부채총계 -> 자본 계정들 -> 자본총계 순서
ASSET_ACCOUNTS = [
    "현금및현금성자산", "매출채권", "계약자산", "재고자산", "유동자산",
    "유형자산", "사용권자산", "무형자산", "영업권", "투자부동산", "관계기업투자", "이연법인세자산",
    "자산총계",
]
LIABILITY_ACCOUNTS = [
    "매입채무", "단기차입금", "유동성장기부채", "유동리스부채", "유동충당부채", "계약부채", "유동부채",
    "장기차입금", "비유동리스부채", "비유동충당부채",
    "부채총계",
]
EQUITY_ACCOUNTS = ["자본금", "이익잉여금", "자기주식", "자본총계"]
BS_ACCOUNTS = ASSET_ACCOUNTS + LIABILITY_ACCOUNTS + EQUITY_ACCOUNTS
IS_ACCOUNTS = [
    "매출액", "매출원가", "매출총이익", "판매비와관리비", "영업이익",
    "금융수익", "금융원가", "법인세비용차감전순이익", "법인세비용", "당기순이익",
]
CF_ACCOUNTS = [
    "영업활동현금흐름", "법인세납부액", "이자지급액",
    "투자활동현금흐름", "유형자산취득액", "유형자산처분액", "무형자산취득액", "무형자산처분액",
    "재무활동현금흐름", "단기차입금유입액", "장기차입금유입액", "단기차입금상환액", "장기차입금상환액",
    "리스부채상환액", "배당금지급액",
]


def format_ratio(value, pct, suffix=None):
    if value is None or pd.isna(value):
        return "-"
    if pct:
        return f"{value * 100:.1f}%"
    if suffix:
        return f"{value:.1f}{suffix}"
    return f"{value:.2f}"


def format_growth_plain(value):
    if value is None or pd.isna(value):
        return "-"
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {abs(value):.1f}%"


def format_growth(value):
    plain = format_growth_plain(value)
    if plain == "-":
        return plain
    css_class = "stat-value-up" if value >= 0 else "stat-value-down"
    return f'<span class="{css_class}">{plain}</span>'


def compute_amt_growth_series(pivot_amt, yr):
    """pivot_amt(회사명 인덱스, 연도 컬럼)에서 yr 시점 전년대비 증감률(%) Series를 계산"""
    if yr not in pivot_amt.columns or (yr - 1) not in pivot_amt.columns:
        return pd.Series(dtype=float)
    prev, curr = pivot_amt[yr - 1], pivot_amt[yr]
    valid = prev.notna() & curr.notna() & (prev != 0)
    return (curr[valid] / prev[valid] - 1) * 100


ACCENT = "#2563eb"
GROWTH_COL = "__growth__"

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }
    iframe[title="st_aggrid.AgGrid.agGrid"] { width: 100% !important; display: block !important; }
    .stat-card {
        position: relative;
        border: 0.8px solid rgba(30, 41, 59, 0.2);
        border-radius: 10px;
        padding: 6px 12px;
        margin-bottom: 0.6rem;
        cursor: help;
    }
    .stat-card[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        left: 50%;
        top: 100%;
        transform: translateX(-50%);
        margin-top: 8px;
        background: #1e293b;
        color: #f1f5f9;
        padding: 8px 12px;
        border-radius: 10px;
        font-size: 0.78rem;
        font-weight: 400;
        line-height: 1.45;
        white-space: normal;
        width: max-content;
        max-width: 240px;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.18);
        z-index: 50;
        pointer-events: none;
    }
    .stat-card[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        left: 50%;
        top: 100%;
        transform: translateX(-50%);
        margin-top: 2px;
        border: 5px solid transparent;
        border-bottom-color: #1e293b;
        z-index: 50;
        pointer-events: none;
    }
    .stat-label { font-size: 0.75rem; color: #64748b; margin-bottom: 0.02rem; }
    .stat-info { color: #94a3b8; font-size: 0.78rem; }
    .stat-value { font-size: 1.05rem; font-weight: 700; color: #1e293b; line-height: 1.15; }
    .stat-value.accent { color: #2563eb; }
    .stat-value-up { color: #dc2626; }
    .stat-value-down { color: #16a34a; }
    .section-title { font-size: 0.95rem; font-weight: 700; margin-bottom: 0.6rem; }
    [data-testid="stAlertContainer"] p { font-size: 0.85rem; }
    /* 재무비율 카드 행은 위쪽 정렬 (기본 stretch면 옆 카드 라벨이 길 때 빈 공간이 생김).
       :has(.stat-card)는 안쪽에 재무비율 카드가 있는 좌/우 패널 전체 행까지 잘못 잡히므로,
       좌/우 패널 행에만 붙인 .twin-panel-row 표시로 그 행만 예외적으로 stretch(기본값)를 되살림 */
    [data-testid="stHorizontalBlock"]:has(.stat-card) { align-items: flex-start; }
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .twin-panel-row) { align-items: stretch; }
    [data-testid="stLayoutWrapper"]:has(.twin-panel-row),
    [data-testid="stVerticalBlock"]:has(.twin-panel-row) {
        height: 100%;
    }
    /* 좌/우 패널 자체 높이는 서로 맞추되, 전체 페이지 스크롤이 생기지 않도록 화면 높이 기준 상한을 두고
       그 안에서는 패널 자체적으로 스크롤 (표/카드가 많은 계정이라도 페이지 전체 스크롤은 안 생기게) */
    [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .twin-panel-row) {
        max-height: calc(100vh - 180px);
        overflow-y: auto;
    }
    [data-testid="stButton"] button[kind="primary"] {
        background: #2563eb !important;
        color: #ffffff !important;
        border: none;
    }
    [data-testid="stButton"] button[kind="primary"]:hover {
        background: #1d4ed8 !important;
    }
    /* AI 챗봇 사이드바를 "밀어내기"가 아니라 "위에 겹쳐서 뜨는" 오버레이로 — 펼쳐도 뒤에 있는
       재무제표/분석 화면 너비가 그대로 유지되도록, 사이드바를 flex 레이아웃에서 빼서 고정 위치로 띄움.
       [data-testid="stSidebar"]를 두 번 반복한 건 실수가 아니라 명시적인 우선순위 트릭 — Streamlit이
       자체적으로 생성하는 .st-emotion-cache-XXXX 클래스 규칙이 min-width/max-width/transform에
       똑같은 specificity(속성 선택자 1개)를 갖고 있어서, 속성 선택자를 하나 더 반복해 specificity를
       올려야 어느 쪽이 DOM에 먼저/나중에 삽입되든 항상 우리 규칙이 이김 */
    [data-testid="stSidebar"][data-testid="stSidebar"] {
        position: fixed !important;
        top: 60px !important;
        left: 0 !important;
        width: 300px !important;
        height: calc(100vh - 60px) !important;
        z-index: 999995 !important;
        transition: none !important;
        box-shadow: 2px 0 16px rgba(0, 0, 0, 0.18);
    }
    /* Streamlit 자체 규칙에 `transition: transform 300ms, min-width 300ms, max-width 300ms;`가
       걸려 있는데, CSS 스펙상 "활성 트랜지션 중인 값"은 !important를 포함한 모든 캐스케이드보다
       우선순위가 높음 — 그래서 위에서 transition을 아예 꺼버려야(위 transition: none) 우리가
       지정하는 max-width/min-width/transform 값이 트랜지션 도중 어중간한 값에 안 눌리고 항상 적용됨 */
    [data-testid="stSidebar"][data-testid="stSidebar"][aria-expanded="true"] {
        transform: none !important;
        max-width: 300px !important;
        min-width: 300px !important;
    }
    [data-testid="stSidebar"][data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(-300px) !important;
    }
    /* 대화가 쌓여도 "사이드바 닫기" 버튼은 맨 위에, 질문 입력창은 맨 아래에 항상 보이도록 고정
       (둘 다 사이드바 안쪽 스크롤 영역(stSidebarContent)의 자식이라 그냥 두면 스크롤에 같이 밀려 올라감) */
    [data-testid="stSidebarHeader"] {
        position: sticky !important;
        top: 0;
        z-index: 10;
        background: #f8fafc;
    }
    /* 사이드바 닫기 버튼이 원래 Streamlit 기본값으로 마우스를 올리기 전까진 visibility:hidden이라
       처음 보는 사람은 그런 버튼이 있는 줄도 모름 — 항상 보이도록 강제 */
    [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
    }
    /* stChatInput을 absolute로 고정하되 폭을 300px처럼 숫자로 박지 않고 left:0/right:0로 맞춤 —
       그러려면 stChatInput과 stSidebar 사이의 모든 조상이 자기 좌표계를 만들지 않도록 position을
       static으로 돌려놔야, stChatInput의 기준이 그 위의 stSidebar(고정폭)가 되어 사이드바 폭이
       얼마든 항상 꽉 참. stSidebarContent뿐 아니라, Streamlit이 위젯마다 자동으로 감싸는
       stElementContainer(내부적으로 항상 position:relative라서 자기가 먼저 기준점이 되어버림)도
       같이 풀어줘야 함 — 안 그러면 bottom:0이 사이드바가 아니라 이 껍데기 div(높이 0으로 붕괴됨)
       기준으로 계산돼서 입력창이 맨 아래가 아니라 엉뚱하게 제목 바로 밑에 붙어버림 */
    [data-testid="stSidebarContent"],
    [data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stChatInput"]) {
        position: static !important;
    }
    [data-testid="stChatInput"] {
        position: absolute !important;
        bottom: 0;
        left: 0;
        right: 0;
        box-sizing: border-box;
        z-index: 999996;
        background: #f8fafc;
        padding: 4px 8px 6px;
    }
    /* Streamlit 자체 입력창 안쪽 여백이 이미 넉넉해서, 우리가 바깥에 padding을 더 두껍게 얹으면
       한 줄짜리 입력창치고 카드가 지나치게 커 보임 — 안쪽 텍스트 영역 자체의 위아래 여백도 줄임 */
    [data-testid="stChatInput"] textarea {
        padding-top: 4px !important;
        padding-bottom: 4px !important;
    }
    /* 입력창이 화면에 고정되면서 그 뒤에 마지막 대화 내용이 가려지지 않도록 스크롤 영역 아래쪽에 여백 확보 */
    [data-testid="stSidebarContent"] {
        padding-bottom: 55px;
    }
    /* 사이드바를 접었을 때 다시 펼치는 버튼이 화살표 아이콘 하나뿐이라 눈에 잘 안 띄어서,
       화면 왼쪽 가장자리에 항상 붙어 있는 세로 탭(책갈피 느낌)으로 재설계 — 원래는 상단 툴바
       안에 있던 인라인 버튼이라, position:fixed로 꺼내서 화면 어디로 스크롤하든 왼쪽에 고정 */
    [data-testid="stExpandSidebarButton"] {
        position: fixed !important;
        left: 0 !important;
        top: 25% !important;
        transform: translateY(-50%) !important;
        background: #2563eb !important;
        border-radius: 0 10px 10px 0 !important;
        width: 34px !important;
        height: auto !important;
        padding: 14px 8px !important;
        display: flex !important;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        z-index: 999997 !important;
        box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.18);
    }
    /* "AI동기"를 그냥 한 줄로 세로쓰기하면 A/I/동/기가 전부 똑같은 간격으로 떨어져 있어서
       "AI"가 한 덩어리로 안 붙어 보임 — text-combine-upright: all은 "AI"처럼 짧은 라틴 문자열을
       회전 없이 하나의 정사각형 글자 폭 안에 가로로 합쳐주는 전용 기능(세로쓰기 일본어/한글
       문서에서 "12"처럼 숫자 두 자리를 붙여 쓸 때 쓰는 것과 동일한 원리) — 그래서 "AI"만 따로
       떼어 이 속성을 적용하고, "동기"는 기존처럼 upright로 세로 스택. 아이콘(실제 자식)은
       flex order로 맨 앞에 오도록 지정 */
    [data-testid="stExpandSidebarButton"] span[data-testid="stIconMaterial"] {
        color: #ffffff !important;
        order: 1;
    }
    [data-testid="stExpandSidebarButton"]::before {
        content: "AI";
        writing-mode: vertical-rl;
        text-combine-upright: all;
        order: 2;
        color: #ffffff;
        font-size: 13px;
        font-weight: 700;
        white-space: nowrap;
    }
    [data-testid="stExpandSidebarButton"]::after {
        content: "동기";
        writing-mode: vertical-rl;
        text-orientation: upright;
        order: 3;
        color: #ffffff;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 1px;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "selected_account" not in st.session_state:
    st.session_state.selected_account = None


def stat_card(label, value, accent=False, desc=None):
    value_class = "stat-value accent" if accent else "stat-value"
    info_html = ' <span class="stat-info">ⓘ</span>' if desc else ""
    tooltip_attr = f' data-tooltip="{html.escape(desc)}"' if desc else ""
    st.markdown(
        f'<div class="stat-card"{tooltip_attr}>'
        f'<div class="stat-label">{label}{info_html}</div>'
        f'<div class="{value_class}">{value}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


db = load_database()
ALL_YEARS = sorted(db["연도"].unique(), reverse=True)

# ---------------- 상단 바 ----------------
with st.container(border=True):
    col_title, col_industry, col_company, col_year = st.columns([2, 1, 1, 1])

    with col_title:
        st.markdown("### 🔍 Audit Copilot")

    industries = sorted(db["업종"].unique())
    companies_all = sorted(db["회사명"].unique())

    def _sync_industry_to_company():
        # 기업을 바꾸면 업종도 그 회사에 맞게 자동으로 갱신
        picked = st.session_state.company_select
        st.session_state.industry_select = db[db["회사명"] == picked]["업종"].iloc[0]

    def _sync_company_to_industry():
        # 업종을 직접 바꾸면 그 업종의 첫 회사로 기업 선택도 같이 전환
        picked = st.session_state.industry_select
        st.session_state.company_select = sorted(db[db["업종"] == picked]["회사명"].unique())[0]

    if "company_select" not in st.session_state:
        st.session_state.company_select = companies_all[0]
    if "industry_select" not in st.session_state:
        st.session_state.industry_select = db[db["회사명"] == st.session_state.company_select]["업종"].iloc[0]

    # 회사를 검색해서 바로 고를 수 있도록 업종 필터 없이 전체 100개 중에서 선택
    # (selectbox는 입력하면 자동으로 목록이 좁혀지는 검색 기능이 기본 내장돼 있음)
    with col_company:
        company = st.selectbox(
            "기업", companies_all, label_visibility="collapsed",
            key="company_select", on_change=_sync_industry_to_company,
        )

    with col_industry:
        industry = st.selectbox(
            "업종", industries, label_visibility="collapsed",
            key="industry_select", on_change=_sync_company_to_industry,
        )

    with col_year:
        year = st.selectbox("연도(당기 기준)", ALL_YEARS, label_visibility="collapsed")

chat_context = f"{industry} 업종의 {company} ({year}년 기준 데이터)를 보고 있음"

st.write("")

left, right = st.columns([1, 1.3])

company_data = db[(db["회사명"] == company) & (db["연도"] == year)]


def render_statement(accounts, grid_key):
    rows = []
    for account in accounts:
        yr_data = db[(db["회사명"] == company) & (db["계정"] == account)]
        if yr_data.empty:
            continue
        row = {"계정과목": account}
        for yr in ALL_YEARS:
            match = yr_data[yr_data["연도"] == yr]
            row[str(yr)] = round(match.iloc[0]["금액"] / 1e8, 1) if not match.empty else None
        rows.append(row)

    table_df = pd.DataFrame(rows)

    value_formatter = JsCode(
        "function(params) { return params.value != null ? params.value.toLocaleString() : '-'; }"
    )

    gb = GridOptionsBuilder.from_dataframe(table_df)
    gb.configure_default_column(resizable=True, sortable=False, filterable=False, flex=1)
    gb.configure_column("계정과목", pinned="left", cellStyle={"fontWeight": "600"}, minWidth=150, flex=2)
    for yr in ALL_YEARS:
        gb.configure_column(
            str(yr),
            type=["numericColumn"],
            valueFormatter=value_formatter,
            cellStyle={"textAlign": "right"},
        )
    gb.configure_selection(selection_mode="single", use_checkbox=False, suppressRowClickSelection=False)
    grid_options = gb.build()

    row_height = 34
    grid_height = min(60 + row_height * max(len(table_df), 1), 1000)

    grid_response = AgGrid(
        table_df,
        gridOptions=grid_options,
        update_on=["selectionChanged"],
        theme="streamlit",
        height=grid_height,
        key=grid_key,
        allow_unsafe_jscode=True,
    )

    selected = grid_response.get("selected_rows")
    if selected is not None and len(selected) > 0:
        if isinstance(selected, pd.DataFrame):
            clicked_account = selected.iloc[0]["계정과목"]
        else:
            clicked_account = selected[0]["계정과목"]
        last_key = f"{grid_key}_last_selected"
        if st.session_state.get(last_key) != clicked_account:
            st.session_state[last_key] = clicked_account
            st.session_state.selected_account = clicked_account
            st.rerun()


# ---------------- 좌측: 재무제표 ----------------
with left:
    with st.container(border=True):
        st.markdown('<span class="twin-panel-row"></span>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📋 재무제표 (억원)</div>', unsafe_allow_html=True)
        tab_bs, tab_is, tab_cf = st.tabs(["재무상태표", "손익계산서", "현금흐름표"])
        with tab_bs:
            render_statement(BS_ACCOUNTS, grid_key=f"grid_bs_{company}_{year}")
        with tab_is:
            render_statement(IS_ACCOUNTS, grid_key=f"grid_is_{company}_{year}")
        with tab_cf:
            render_statement(CF_ACCOUNTS, grid_key=f"grid_cf_{company}_{year}")

# ---------------- 우측: 선택 계정 분석 ----------------
with right:
    with st.container(border=True):
        st.markdown('<span class="twin-panel-row"></span>', unsafe_allow_html=True)
        selected_account = st.session_state.selected_account

        if not selected_account:
            st.markdown('<div class="section-title">🔎 선택 계정 분석</div>', unsafe_allow_html=True)
            st.info("왼쪽 표에서 계정명을 클릭하면 분석이 표시됩니다.")
        elif selected_account not in CLICKABLE_ACCOUNTS:
            st.markdown(
                f'<div class="section-title">🔎 {selected_account}</div>', unsafe_allow_html=True
            )
            st.info("이 계정은 아직 상세 분석을 지원하지 않습니다.")
        else:
            st.markdown(
                f'<div class="section-title">🔎 {selected_account} 분석</div>',
                unsafe_allow_html=True,
            )

            include_contract = False
            has_combined_warning = False

            if selected_account in ("매출채권", "매입채무"):
                combined_warning = company_data[
                    (company_data["계정"] == selected_account) & (company_data["경고"] != "")
                ]
                has_combined_warning = not combined_warning.empty
                if has_combined_warning:
                    st.warning(combined_warning.iloc[0]["경고"])

            if selected_account == "매출채권":
                has_contract = not company_data[company_data["계정"] == "계약자산"].empty
                if has_contract:
                    include_contract = st.checkbox("계약자산(미청구공사) 포함해서 계산", value=False)
                    if include_contract:
                        st.caption("ℹ️ " + CONTRACT_ASSET_NOTE)

            ratios = compute_company_ratios(db, include_contract_asset=include_contract)
            row = ratios[(ratios["회사명"] == company) & (ratios["연도"] == year)].iloc[0]

            ratio_family = RATIO_FAMILIES[selected_account]
            growth_meta = {"col": GROWTH_COL, "label": "증감률", "pct": False, "suffix": None}
            chart_options = [growth_meta] + ratio_family
            primary_ratio = ratio_family[0] if ratio_family else growth_meta

            trend = (
                db[(db["회사명"] == company) & (db["계정"] == selected_account)][["연도", "금액"]]
                .sort_values("연도")
            )
            amt_series = trend.set_index("연도")["금액"]
            yoy = None
            if year in amt_series.index and (year - 1) in amt_series.index and amt_series[year - 1]:
                yoy = (amt_series[year] / amt_series[year - 1] - 1) * 100

            industry_amt = (
                db[(db["업종"] == industry) & (db["계정"] == selected_account)][["회사명", "연도", "금액"]]
                .pivot_table(index="회사명", columns="연도", values="금액", aggfunc="first")
            )
            peer_growth_now = compute_amt_growth_series(industry_amt, year)
            industry_yoy = peer_growth_now.mean() if not peer_growth_now.empty else None

            c1, c2 = st.columns(2)
            with c1:
                stat_card(f"{selected_account} 증감률", format_growth(yoy), accent=True)
            with c2:
                stat_card(f"산업 평균 {selected_account} 증감률", format_growth(industry_yoy))

            for ratio_meta in ratio_family:
                r_col, r_label, r_pct = ratio_meta["col"], ratio_meta["label"], ratio_meta["pct"]
                r_suffix = ratio_meta.get("suffix")
                r_desc = ratio_meta.get("desc")
                r_avg = compute_industry_average(ratios, industry, year, r_col)
                c1, c2 = st.columns(2)
                with c1:
                    stat_card(
                        r_label,
                        format_ratio(row.get(r_col), r_pct, r_suffix),
                        accent=True,
                        desc=r_desc,
                    )
                with c2:
                    stat_card(
                        f"산업 평균 {r_label}",
                        format_ratio(r_avg, r_pct, r_suffix),
                        desc=r_desc,
                    )

            st.write("")

            # ---- 시각화: 재무비율 선택 + 차트 종류 선택 (버튼 조합으로 하나만 표시) ----
            ratio_state_key = f"viz_ratio::{selected_account}"
            chart_state_key = f"viz_chart::{selected_account}"
            if ratio_state_key not in st.session_state:
                st.session_state[ratio_state_key] = primary_ratio["col"]
            if chart_state_key not in st.session_state:
                st.session_state[chart_state_key] = "추세그래프"

            selected_ratio_col = st.session_state[ratio_state_key]
            selected_ratio_meta = next(
                (rm for rm in chart_options if rm["col"] == selected_ratio_col), primary_ratio
            )

            ratio_btn_cols = st.columns(len(chart_options))
            for i, opt_meta in enumerate(chart_options):
                with ratio_btn_cols[i]:
                    is_selected = opt_meta["col"] == selected_ratio_col
                    if st.button(
                        opt_meta["label"],
                        key=f"ratiobtn_{selected_account}_{opt_meta['col']}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                    ):
                        st.session_state[ratio_state_key] = opt_meta["col"]
                        st.rerun()

            if selected_ratio_col == GROWTH_COL:
                selected_value = yoy
                selected_avg = industry_yoy
                peers = (
                    peer_growth_now.rename(GROWTH_COL).reset_index()
                    .dropna(subset=[GROWTH_COL])
                    .sort_values(GROWTH_COL, ascending=False)
                    .reset_index(drop=True)
                )
                stats = compute_growth_boxplot_stats(peer_growth_now, company)
                format_selected = format_growth_plain
            else:
                selected_value = row.get(selected_ratio_col)
                selected_avg = compute_industry_average(ratios, industry, year, selected_ratio_col)
                peers = (
                    ratios[(ratios["업종"] == industry) & (ratios["연도"] == year)][["회사명", selected_ratio_col]]
                    .dropna(subset=[selected_ratio_col])
                    .sort_values(selected_ratio_col, ascending=False)
                    .reset_index(drop=True)
                )
                stats = compute_boxplot_stats(ratios, industry, year, selected_ratio_col, company)
                format_selected = (
                    lambda v: format_ratio(v, selected_ratio_meta["pct"], selected_ratio_meta.get("suffix"))
                )

            chat_context += (
                f"\n현재 '{selected_account}' 계정의 {selected_ratio_meta['label']}을 확인 중: "
                f"{company} {format_selected(selected_value)} (업종 평균 {format_selected(selected_avg)})"
                f"{', 업종 내 이상치 구간' if stats['is_outlier'] else ''}"
            )

            selected_chart_type = st.session_state[chart_state_key]

            chart_types = ["추세그래프", "박스플롯", "순위"]
            chart_btn_cols = st.columns(len(chart_types))
            for i, ct in enumerate(chart_types):
                with chart_btn_cols[i]:
                    btn_label = "⚠️ 박스플롯" if (ct == "박스플롯" and stats["is_outlier"]) else ct
                    is_selected = ct == selected_chart_type
                    if st.button(
                        btn_label,
                        key=f"charttype_{selected_account}_{ct}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                    ):
                        st.session_state[chart_state_key] = ct
                        st.rerun()

            if selected_chart_type == "추세그래프":
                trend_rows = []
                if selected_ratio_col == GROWTH_COL:
                    for yr in sorted(ALL_YEARS):
                        yr_growth = compute_amt_growth_series(industry_amt, yr)
                        if company in yr_growth.index and pd.notna(yr_growth[company]):
                            trend_rows.append({"연도": yr, "값": yr_growth[company], "구분": company})
                        if not yr_growth.empty:
                            trend_rows.append({"연도": yr, "값": yr_growth.mean(), "구분": "산업 평균"})
                else:
                    for yr in sorted(ALL_YEARS):
                        yr_row = ratios[(ratios["회사명"] == company) & (ratios["연도"] == yr)]
                        if not yr_row.empty and pd.notna(yr_row.iloc[0][selected_ratio_col]):
                            trend_rows.append({"연도": yr, "값": yr_row.iloc[0][selected_ratio_col], "구분": company})
                        yr_avg = compute_industry_average(ratios, industry, yr, selected_ratio_col)
                        if yr_avg is not None:
                            trend_rows.append({"연도": yr, "값": yr_avg, "구분": "산업 평균"})

                trend_ratio_df = pd.DataFrame(trend_rows)
                trend_chart = (
                    alt.Chart(trend_ratio_df)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("연도:O"),
                        y=alt.Y("값:Q", title=selected_ratio_meta["label"]),
                        color=alt.Color(
                            "구분:N",
                            scale=alt.Scale(domain=[company, "산업 평균"], range=[ACCENT, "#94a3b8"]),
                            legend=alt.Legend(title=None),
                        ),
                    )
                )
                st.altair_chart(trend_chart, use_container_width=True)

            elif selected_chart_type == "박스플롯":
                if stats["is_outlier"]:
                    st.error(
                        f"⚠️ {company}의 {selected_ratio_meta['label']}({stats['company_value']})이 "
                        f"업종 중앙값({stats['median']})에서 크게 벗어난 이상치 구간입니다."
                    )
                else:
                    st.caption(
                        f"업종 분포: 최소 {stats['min']} · Q1 {stats['q1']} · 중앙값 {stats['median']} "
                        f"· Q3 {stats['q3']} · 최대 {stats['max']}"
                    )

                box_source = peers.copy()
                box_source["업종"] = industry
                box_chart = (
                    alt.Chart(box_source)
                    .mark_boxplot(color="#94a3b8", size=50, opacity=0.5)
                    .encode(x=alt.X("업종:N", title=None), y=alt.Y(f"{selected_ratio_col}:Q", title=selected_ratio_meta["label"]))
                )
                strip_chart = (
                    alt.Chart(box_source)
                    .transform_calculate(jitter="random()")
                    .mark_circle(size=60, color="#1e293b", opacity=0.75)
                    .encode(
                        x=alt.X("업종:N", title=None),
                        y=alt.Y(f"{selected_ratio_col}:Q"),
                        xOffset=alt.XOffset("jitter:Q", scale=alt.Scale(domain=[0, 1], range=[-30, 30])),
                        tooltip=["회사명", selected_ratio_col],
                    )
                )
                point_chart = (
                    alt.Chart(pd.DataFrame({"업종": [industry], "값": [selected_value]}))
                    .mark_point(shape="diamond", size=200, color="#f97316", filled=True)
                    .encode(x="업종:N", y="값:Q")
                )
                st.altair_chart(box_chart + strip_chart + point_chart, use_container_width=True)

            else:
                rank_chart = (
                    alt.Chart(peers)
                    .mark_bar()
                    .encode(
                        x=alt.X(f"{selected_ratio_col}:Q", title=selected_ratio_meta["label"]),
                        y=alt.Y("회사명:N", sort="-x", title=None),
                        color=alt.condition(
                            alt.datum.회사명 == company,
                            alt.value(ACCENT),
                            alt.value("#94a3b8"),
                        ),
                    )
                )
                st.altair_chart(rank_chart, use_container_width=True)

            st.write("")

            if st.button("🤖 AI 추천 감사 질문", use_container_width=True, type="primary"):
                if not os.path.exists("standards_chunks.json"):
                    st.warning("아직 감사기준서 데이터베이스가 준비되지 않았습니다 (백그라운드 작업 진행 중일 수 있어요).")
                else:
                    try:
                        with st.spinner("관련 감사기준서를 검색하고 질문을 생성하는 중..."):
                            context = {
                                "회사명": company,
                                "계정": selected_account,
                                "지표명": selected_ratio_meta["label"],
                                "지표값": format_selected(selected_value),
                                "업종": industry,
                                "업종평균": format_selected(selected_avg),
                                "이상치": stats["is_outlier"],
                                "당기금액_증감률": yoy,
                                "통합계정_경고": has_combined_warning,
                                "계약자산_포함": include_contract,
                            }
                            result = generate_audit_questions(context)
                        st.markdown(result["questions_text"])
                        st.caption("참고한 감사기준서: " + ", ".join(result["retrieved_standards"]))
                    except genai_errors.ClientError as e:
                        if "RESOURCE_EXHAUSTED" in str(e):
                            st.error("Gemini API 일일 사용량 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
                        else:
                            st.error(f"Gemini API 호출 중 오류가 발생했습니다: {e}")
                    except genai_errors.ServerError:
                        st.error("Gemini 서버가 일시적으로 혼잡합니다. 잠시 후 버튼을 다시 눌러주세요.")

# ---------------- 사이드바: AI 동기 챗봇 ----------------
with st.sidebar:
    st.markdown("### 💬 AI 동기")
    st.caption("지금 화면에서 보고 있는 회사·계정을 참고해서 편하게 물어보세요.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            if msg.get("error"):
                st.error(msg["text"])
            else:
                st.markdown(msg["text"])

    user_input = st.chat_input("궁금한 거 물어봐...")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "text": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("생각 중..."):
                error_text = None
                try:
                    history = [
                        {"role": "user" if m["role"] == "user" else "model", "text": m["text"]}
                        for m in st.session_state.chat_messages[:-1]
                    ]
                    reply = generate_chat_reply(chat_context, history, user_input)
                    st.markdown(reply)
                    st.session_state.chat_messages.append({"role": "assistant", "text": reply})
                except genai_errors.ClientError as e:
                    if "RESOURCE_EXHAUSTED" in str(e):
                        error_text = "⚠️ Gemini API 일일 사용량을 다 썼나봐. 잠시 후에 다시 물어봐줄래?"
                    else:
                        error_text = f"⚠️ API 호출 중 오류가 났어: {e}"
                except genai_errors.ServerError:
                    error_text = "⚠️ Gemini 서버가 지금 좀 혼잡한가봐. 잠깐 있다가 다시 물어봐줄래?"

                if error_text:
                    st.error(error_text)
                    st.session_state.chat_messages.append({"role": "assistant", "text": error_text, "error": True})
