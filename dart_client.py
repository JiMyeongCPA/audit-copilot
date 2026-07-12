import json
import pandas as pd
import opendartreader
from config import API_KEY

dart = opendartreader.OpenDartReader(API_KEY)

DISCOVERY_LOG = "discovered_tags.jsonl"

TEXT_MATCH_WARNING = (
    "표준 계정코드(account_id)로 찾지 못해, 계정명 텍스트로 대신 찾은 값입니다. "
    "회사 고유 계정코드를 쓰는 경우일 수 있으니 정확성을 별도로 확인하세요."
)

# 계정 개념별 정의: 확인된 표준 태그(우선순위 순) + 태그가 없을 때 계정명 텍스트로 찾기 위한 키워드.
# tags에서 못 찾으면 keywords로 account_nm을 검색하고, exclude에 있는 단어가 포함된 행은 제외함
# (예: "매출채권" 검색 시 "장기매출채권"처럼 다른 개념까지 잘못 잡히는 것 방지).
ACCOUNT_DEFINITIONS = {
    "매출액": {"tags": ["ifrs-full_Revenue"], "keywords": ["매출액"], "exclude": []},
    "매출원가": {"tags": ["ifrs-full_CostOfSales"], "keywords": ["매출원가"], "exclude": []},
    "재고자산": {"tags": ["ifrs-full_Inventories"], "keywords": ["재고자산"], "exclude": []},
    "현금및현금성자산": {"tags": ["ifrs-full_CashAndCashEquivalents"], "keywords": ["현금및현금성자산"], "exclude": []},
    "유동자산": {"tags": ["ifrs-full_CurrentAssets"], "keywords": ["유동자산"], "exclude": ["비유동"]},
    "유동부채": {"tags": ["ifrs-full_CurrentLiabilities"], "keywords": ["유동부채"], "exclude": ["비유동"]},
    "단기차입금": {"tags": ["ifrs-full_ShorttermBorrowings"], "keywords": ["단기차입금", "단기금융부채"], "exclude": []},
    "유동성장기부채": {
        "tags": ["ifrs-full_CurrentPortionOfLongtermBorrowings"],
        "keywords": ["유동성장기부채"],
        "exclude": ["단기차입금"],
    },
    "장기차입금": {
        "tags": ["ifrs-full_LongtermBorrowings", "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived"],
        "keywords": ["장기차입금", "장기금융부채"],
        "exclude": ["유동성"],
    },
    "부채총계": {"tags": ["ifrs-full_Liabilities"], "keywords": ["부채총계"], "exclude": []},
    "자본총계": {"tags": ["ifrs-full_Equity"], "keywords": ["자본총계"], "exclude": []},
    "자산총계": {"tags": ["ifrs-full_Assets"], "keywords": ["자산총계"], "exclude": []},
    "영업이익": {"tags": ["dart_OperatingIncomeLoss"], "keywords": ["영업이익"], "exclude": []},
    "당기순이익": {"tags": ["ifrs-full_ProfitLoss"], "keywords": ["당기순이익"], "exclude": []},
    "금융원가": {"tags": ["ifrs-full_FinanceCosts"], "keywords": ["금융원가"], "exclude": []},
    # 2단계 확장 (2026-07-09)
    "유형자산": {"tags": ["ifrs-full_PropertyPlantAndEquipment"], "keywords": ["유형자산"], "exclude": []},
    "사용권자산": {"tags": ["ifrs-full_RightofuseAssets"], "keywords": ["사용권자산"], "exclude": []},
    "무형자산": {
        "tags": ["ifrs-full_IntangibleAssetsOtherThanGoodwill", "ifrs-full_IntangibleAssetsAndGoodwill"],
        "keywords": ["무형자산"],
        "exclude": ["영업권"],
    },
    "영업권": {"tags": ["ifrs-full_Goodwill"], "keywords": ["영업권"], "exclude": ["이외"]},
    "투자부동산": {"tags": ["ifrs-full_InvestmentProperty"], "keywords": ["투자부동산"], "exclude": []},
    "관계기업투자": {
        "tags": [
            "ifrs-full_InvestmentsInAssociatesAndJointVenturesAccountedForUsingEquityMethod",
            "ifrs-full_InvestmentAccountedForUsingEquityMethod",
        ],
        "keywords": ["관계기업", "관계회사"],
        "exclude": [],
    },
    "이연법인세자산": {
        "tags": ["ifrs-full_DeferredTaxAssets", "ifrs-full_NetDeferredTaxAssets"],
        "keywords": ["이연법인세자산"],
        "exclude": [],
    },
    "유동충당부채": {
        "tags": ["ifrs-full_CurrentProvisions", "ifrs-full_OtherShorttermProvisions"],
        "keywords": ["유동충당부채", "충당부채"],
        "exclude": ["비유동", "장기"],
    },
    "비유동충당부채": {
        "tags": ["ifrs-full_NoncurrentProvisions", "ifrs-full_OtherLongtermProvisions"],
        "keywords": ["비유동충당부채", "장기충당부채"],
        "exclude": [],
    },
    "계약부채": {"tags": ["ifrs-full_CurrentContractLiabilities"], "keywords": ["계약부채"], "exclude": []},
    "자본금": {"tags": ["ifrs-full_IssuedCapital"], "keywords": ["자본금"], "exclude": ["기타"]},
    "이익잉여금": {"tags": ["ifrs-full_RetainedEarnings"], "keywords": ["이익잉여금"], "exclude": []},
    "자기주식": {"tags": ["ifrs-full_TreasuryShares"], "keywords": ["자기주식"], "exclude": []},
    "매출총이익": {"tags": ["ifrs-full_GrossProfit"], "keywords": ["매출총이익"], "exclude": []},
    "판매비와관리비": {
        "tags": ["dart_TotalSellingGeneralAdministrativeExpenses", "ifrs-full_SellingGeneralAndAdministrativeExpense"],
        "keywords": ["판매비와관리비", "판매비및관리비"],
        "exclude": [],
    },
    "금융수익": {"tags": ["ifrs-full_FinanceIncome"], "keywords": ["금융수익"], "exclude": []},
    "법인세비용차감전순이익": {
        "tags": ["ifrs-full_ProfitLossBeforeTax"],
        "keywords": ["법인세비용차감전순이익", "법인세차감전순이익"],
        "exclude": [],
    },
    "법인세비용": {
        "tags": ["ifrs-full_IncomeTaxExpenseContinuingOperations"],
        "keywords": ["법인세비용"],
        "exclude": ["차감전"],
    },
    # 현금흐름표 확장 (2026-07-10)
    "유동리스부채": {"tags": ["ifrs-full_CurrentLeaseLiabilities"], "keywords": ["유동리스부채", "유동성리스부채"], "exclude": ["비유동"]},
    "비유동리스부채": {"tags": ["ifrs-full_NoncurrentLeaseLiabilities"], "keywords": ["비유동리스부채", "리스부채"], "exclude": ["유동"]},
    "영업활동현금흐름": {
        "tags": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
        "keywords": ["영업활동으로 인한 현금흐름", "영업활동현금흐름"],
        "exclude": [],
    },
    "투자활동현금흐름": {
        "tags": ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
        "keywords": ["투자활동으로 인한 현금흐름", "투자활동현금흐름"],
        "exclude": [],
    },
    "재무활동현금흐름": {
        "tags": ["ifrs-full_CashFlowsFromUsedInFinancingActivities"],
        "keywords": ["재무활동으로 인한 현금흐름", "재무활동현금흐름"],
        "exclude": [],
    },
    "유형자산취득액": {
        "tags": ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
        "keywords": ["유형자산의 취득"],
        "exclude": [],
    },
    "무형자산취득액": {
        "tags": ["ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"],
        "keywords": ["무형자산의 취득"],
        "exclude": [],
    },
    "유형자산처분액": {
        "tags": ["ifrs-full_ProceedsFromSalesOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
        "keywords": ["유형자산의 처분"],
        "exclude": [],
    },
    "무형자산처분액": {
        "tags": ["ifrs-full_ProceedsFromSalesOfIntangibleAssetsClassifiedAsInvestingActivities"],
        "keywords": ["무형자산의 처분"],
        "exclude": [],
    },
    "배당금지급액": {
        "tags": ["ifrs-full_DividendsPaidClassifiedAsFinancingActivities"],
        "keywords": ["배당금의 지급", "배당금 지급"],
        "exclude": [],
    },
    "법인세납부액": {
        "tags": [
            "ifrs-full_IncomeTaxesPaidRefundClassifiedAsOperatingActivities",
            "ifrs-full_IncomeTaxesPaidClassifiedAsOperatingActivities",
        ],
        "keywords": ["법인세의 납부", "법인세 납부액", "법인세환급"],
        "exclude": [],
    },
    "이자지급액": {
        "tags": [
            "ifrs-full_InterestPaidClassifiedAsOperatingActivities",
            "ifrs-full_InterestPaidClassifiedAsFinancingActivities",
        ],
        "keywords": ["이자의 지급"],
        "exclude": [],
    },
    "리스부채상환액": {
        "tags": [
            "ifrs-full_PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities",
            "dart_PaymentsOfFinanceLeaseLiabilitiesClassifiedAsFinancingActivities",
        ],
        "keywords": ["리스부채의 상환", "리스부채의 감소"],
        "exclude": [],
    },
    "단기차입금유입액": {
        "tags": ["dart_ProceedsFromShortTermBorrowings", "ifrs-full_ProceedsFromCurrentBorrowings"],
        "keywords": ["단기차입금의 차입", "유동차입금의 증가"],
        "exclude": [],
    },
    "장기차입금유입액": {
        "tags": ["dart_ProceedsFromLongTermBorrowings", "ifrs-full_ProceedsFromNoncurrentBorrowings"],
        "keywords": ["장기차입금의 차입", "비유동차입금의 증가"],
        "exclude": [],
    },
    "단기차입금상환액": {
        "tags": [
            "dart_RepaymentsOfShortTermBorrowings",
            "ifrs-full_RepaymentsOfCurrentBorrowings",
            "ifrs-full_RepaymentsOfShortTermBorrowings",
        ],
        "keywords": ["단기차입금의 상환", "유동차입금의 상환"],
        "exclude": [],
    },
    "장기차입금상환액": {
        "tags": [
            "dart_RepaymentsOfLongTermBorrowings",
            "ifrs-full_RepaymentsOfNoncurrentBorrowings",
            "ifrs-full_RepaymentsOfLongTermBorrowings",
        ],
        "keywords": ["장기차입금의 상환", "비유동차입금의 상환"],
        "exclude": [],
    },
}

# 계정이 어느 재무제표에 속하는지 (화면에서 재무상태표/손익계산서 탭으로 나눌 때 사용)
ACCOUNT_STATEMENT_MAP = {
    "매출액": "손익계산서",
    "매출원가": "손익계산서",
    "영업이익": "손익계산서",
    "당기순이익": "손익계산서",
    "금융원가": "손익계산서",
    "재고자산": "재무상태표",
    "매출채권": "재무상태표",
    "계약자산": "재무상태표",
    "현금및현금성자산": "재무상태표",
    "유동자산": "재무상태표",
    "유동부채": "재무상태표",
    "매입채무": "재무상태표",
    "단기차입금": "재무상태표",
    "유동성장기부채": "재무상태표",
    "장기차입금": "재무상태표",
    "부채총계": "재무상태표",
    "자본총계": "재무상태표",
    "자산총계": "재무상태표",
    "유형자산": "재무상태표",
    "사용권자산": "재무상태표",
    "무형자산": "재무상태표",
    "영업권": "재무상태표",
    "투자부동산": "재무상태표",
    "관계기업투자": "재무상태표",
    "이연법인세자산": "재무상태표",
    "유동충당부채": "재무상태표",
    "비유동충당부채": "재무상태표",
    "계약부채": "재무상태표",
    "자본금": "재무상태표",
    "이익잉여금": "재무상태표",
    "자기주식": "재무상태표",
    "매출총이익": "손익계산서",
    "판매비와관리비": "손익계산서",
    "금융수익": "손익계산서",
    "법인세비용차감전순이익": "손익계산서",
    "법인세비용": "손익계산서",
    "유동리스부채": "재무상태표",
    "비유동리스부채": "재무상태표",
    "영업활동현금흐름": "현금흐름표",
    "투자활동현금흐름": "현금흐름표",
    "재무활동현금흐름": "현금흐름표",
    "유형자산취득액": "현금흐름표",
    "무형자산취득액": "현금흐름표",
    "유형자산처분액": "현금흐름표",
    "무형자산처분액": "현금흐름표",
    "배당금지급액": "현금흐름표",
    "법인세납부액": "현금흐름표",
    "이자지급액": "현금흐름표",
    "리스부채상환액": "현금흐름표",
    "단기차입금유입액": "현금흐름표",
    "장기차입금유입액": "현금흐름표",
    "단기차입금상환액": "현금흐름표",
    "장기차입금상환액": "현금흐름표",
}

# 매출채권: 순수 매출채권 태그를 우선 사용하고, 없으면 "매출채권및기타채권" 통합 태그로 대체.
# (일부 회사는 매출채권을 기타채권과 합쳐서 한 줄로만 공시하며, 이 경우 둘을 분리할 방법이 없음)
RECEIVABLE_TAGS = [
    ("ifrs-full_CurrentTradeReceivables", False),
    ("ifrs-full_TradeAndOtherCurrentReceivables", True),
]
RECEIVABLE_KEYWORDS = ["매출채권"]
RECEIVABLE_EXCLUDE = ["장기", "미청구", "계약"]

RECEIVABLE_COMBINED_WARNING = (
    "본 계정은 재무상태표상 매출채권및기타채권으로 통합 표시되어 있으므로, "
    "매출채권 회전율 분석 전 주석상 세부 구성 내역을 확인할 필요가 있습니다. "
    "기타채권 비중이 유의적인 경우 매출채권 관련 분석 결과가 왜곡될 수 있습니다."
)

# 매입채무: 순수 매입채무 태그를 우선 사용하고, 없으면 "매입채무및기타채무" 통합 태그로 대체.
# (매출채권과 동일한 논리 — 일부 회사는 매입채무를 기타채무와 합쳐서 한 줄로만 공시함)
PAYABLE_TAGS = [
    ("ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", False),
    ("dart_ShortTermTradePayables", False),
    ("ifrs-full_TradeAndOtherCurrentPayables", True),
]
PAYABLE_KEYWORDS = ["매입채무"]
PAYABLE_EXCLUDE = ["장기"]

PAYABLE_COMBINED_WARNING = (
    "본 계정은 재무상태표상 매입채무및기타채무로 통합 표시되어 있으므로, "
    "매입채무 관련 분석 전 주석상 세부 구성 내역을 확인할 필요가 있습니다. "
    "기타채무 비중이 유의적인 경우 매입채무 관련 분석 결과가 왜곡될 수 있습니다."
)

# 계약자산(미청구공사): 진행기준으로 이미 인식한 수익 중 아직 청구되지 않은 금액.
# 매출채권과 달리 청구권이 아직 확정되지 않았다는 성격 차이가 있어, 자동 합산하지 않고
# 별도 계정으로 남겨둔 뒤 분석 시점에 포함 여부를 선택할 수 있게 함.
CONTRACT_ASSET_TAGS = [
    "dart_ShortTermDueFromCustomersForContractWorkNet",  # 미청구공사
    "ifrs-full_CurrentContractAssets",  # 계약자산
]
CONTRACT_ASSET_KEYWORDS = ["계약자산", "미청구공사"]
CONTRACT_ASSET_EXCLUDE = ["장기", "비유동"]

CONTRACT_ASSET_NOTE = (
    "계약자산(미청구공사)은 진행기준으로 인식한 수익 중 아직 청구되지 않은 금액으로, "
    "매출채권과 달리 청구권이 확정되지 않았습니다. 공사 진행률 및 수익 인식의 적정성에 따라 "
    "금액이 달라질 수 있으므로, 매출채권 회전율 분석에 포함할지 별도로 판단하시기 바랍니다."
)


def _to_num(x):
    return pd.to_numeric(x, errors="coerce")


def _log_discovery(concept, account_id, account_nm, corp_name):
    entry = {"개념": concept, "account_id": account_id, "account_nm": account_nm, "회사": corp_name}
    with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _row_to_dict(r, label, is_combined=False, warning=None):
    return {
        "account_label": label,
        "account_nm": r["account_nm"],
        "thstrm_amount": _to_num(r["thstrm_amount"]),
        "frmtrm_amount": _to_num(r["frmtrm_amount"]),
        "bfefrmtrm_amount": _to_num(r["bfefrmtrm_amount"]),
        "is_combined": is_combined,
        "warning": warning,
    }


def _find_by_tags(raw, tags):
    for tag in tags:
        match = raw[raw["account_id"] == tag]
        if not match.empty:
            return match.iloc[0]
    return None


def _find_by_keywords(raw, keywords, exclude, known_tags, expected_statement=None):
    mask = raw["account_nm"].str.contains("|".join(keywords), na=False)
    for word in exclude:
        mask &= ~raw["account_nm"].str.contains(word, na=False)
    if expected_statement:
        mask &= raw["sj_nm"] == expected_statement
    candidates = raw[mask & ~raw["account_id"].isin(known_tags)]
    if len(candidates) == 1:
        return candidates.iloc[0]
    return None  # 0개(없음) 또는 여러개(모호함)면 포기 — 지어내지 않음


def _extract_row(raw, concept, definition, corp_name):
    """표준 태그로 먼저 찾고, 없으면 계정명 텍스트로 대신 찾음 (찾으면 discovered_tags.jsonl에 기록)"""
    row = _find_by_tags(raw, definition["tags"])
    if row is not None:
        return _row_to_dict(row, concept)

    expected_statement = ACCOUNT_STATEMENT_MAP.get(concept)
    fallback = _find_by_keywords(
        raw, definition["keywords"], definition.get("exclude", []), definition["tags"], expected_statement
    )
    if fallback is not None:
        _log_discovery(concept, fallback["account_id"], fallback["account_nm"], corp_name)
        return _row_to_dict(fallback, concept, warning=TEXT_MATCH_WARNING)

    return None


def get_account_data(corp_name, year):
    """회사명 + 연도 -> 매출/재고/계약자산 관련 계정만 뽑은 표 (당기/전기/전전기 포함)

    표준 계정코드(account_id)로 못 찾으면 계정명 텍스트로 한 번 더 찾아봄 (회사 고유 코드 대응).
    매출채권과 계약자산(미청구공사)은 서로 다른 행으로 분리해서 반환함 —
    합칠지 말지는 분석 단계(compute_turnover_ratios)에서 선택.
    """
    raw = dart.finstate_all(corp_name, year)

    rows = []

    for concept, definition in ACCOUNT_DEFINITIONS.items():
        row = _extract_row(raw, concept, definition, corp_name)
        if row:
            rows.append(row)

    receivable_row = None
    for account_id, is_combined in RECEIVABLE_TAGS:
        match = raw[raw["account_id"] == account_id]
        if not match.empty:
            warning = RECEIVABLE_COMBINED_WARNING if is_combined else None
            receivable_row = _row_to_dict(match.iloc[0], "매출채권", is_combined=is_combined, warning=warning)
            break

    if receivable_row is None:
        fallback = _find_by_keywords(
            raw, RECEIVABLE_KEYWORDS, RECEIVABLE_EXCLUDE, [t for t, _ in RECEIVABLE_TAGS],
            ACCOUNT_STATEMENT_MAP["매출채권"],
        )
        if fallback is not None:
            _log_discovery("매출채권", fallback["account_id"], fallback["account_nm"], corp_name)
            receivable_row = _row_to_dict(fallback, "매출채권", is_combined=True, warning=TEXT_MATCH_WARNING)

    if receivable_row:
        rows.append(receivable_row)

    payable_row = None
    for account_id, is_combined in PAYABLE_TAGS:
        match = raw[raw["account_id"] == account_id]
        if not match.empty:
            warning = PAYABLE_COMBINED_WARNING if is_combined else None
            payable_row = _row_to_dict(match.iloc[0], "매입채무", is_combined=is_combined, warning=warning)
            break

    if payable_row is None:
        fallback = _find_by_keywords(
            raw, PAYABLE_KEYWORDS, PAYABLE_EXCLUDE, [t for t, _ in PAYABLE_TAGS],
            ACCOUNT_STATEMENT_MAP["매입채무"],
        )
        if fallback is not None:
            _log_discovery("매입채무", fallback["account_id"], fallback["account_nm"], corp_name)
            payable_row = _row_to_dict(fallback, "매입채무", is_combined=True, warning=TEXT_MATCH_WARNING)

    if payable_row:
        rows.append(payable_row)

    contract_row = None
    for account_id in CONTRACT_ASSET_TAGS:
        match = raw[raw["account_id"] == account_id]
        if not match.empty:
            contract_row = _row_to_dict(match.iloc[0], "계약자산")
            break

    if contract_row is None:
        fallback = _find_by_keywords(
            raw, CONTRACT_ASSET_KEYWORDS, CONTRACT_ASSET_EXCLUDE, CONTRACT_ASSET_TAGS,
            ACCOUNT_STATEMENT_MAP["계약자산"],
        )
        if fallback is not None:
            _log_discovery("계약자산", fallback["account_id"], fallback["account_nm"], corp_name)
            contract_row = _row_to_dict(fallback, "계약자산", warning=TEXT_MATCH_WARNING)

    if contract_row:
        rows.append(contract_row)

    return pd.DataFrame(rows)


def compute_turnover_ratios(df, include_contract_asset=False):
    """매출채권회전율(매출액/매출채권), 재고자산회전율(매출원가/재고자산)을 당기/전기/전전기로 계산

    include_contract_asset=True면 계약자산(미청구공사)을 매출채권에 더해서 계산함.
    """
    periods = {
        "당기": "thstrm_amount",
        "전기": "frmtrm_amount",
        "전전기": "bfefrmtrm_amount",
    }

    def get_amount(label, col):
        row = df[df["account_label"] == label]
        if row.empty or pd.isna(row.iloc[0][col]):
            return None
        return row.iloc[0][col]

    receivable_row = df[df["account_label"] == "매출채권"]
    receivable_warning = None
    if not receivable_row.empty and receivable_row.iloc[0]["is_combined"]:
        receivable_warning = receivable_row.iloc[0]["warning"]

    has_contract_asset = not df[df["account_label"] == "계약자산"].empty

    results = []
    for period_label, col in periods.items():
        revenue = get_amount("매출액", col)
        cogs = get_amount("매출원가", col)
        receivables = get_amount("매출채권", col)
        contract_asset = get_amount("계약자산", col)
        inventory = get_amount("재고자산", col)

        effective_receivables = receivables
        if include_contract_asset and contract_asset:
            effective_receivables = (receivables or 0) + contract_asset

        results.append({
            "기간": period_label,
            "매출채권회전율": round(revenue / effective_receivables, 2) if revenue and effective_receivables else None,
            "재고자산회전율": round(cogs / inventory, 2) if cogs and inventory else None,
            "매출채권_경고": receivable_warning,
            "계약자산_존재": has_contract_asset,
            "계약자산_포함여부": include_contract_asset,
        })

    return results


def to_long_format(df, corp_name, industry, base_year):
    """계정 데이터를 '업종/회사명/연도/계정/금액/경고' 한 줄짜리 형태로 변환 (DB 저장용)

    매출채권과 계약자산은 각자 별도 '계정' 행으로 저장됨 (합산은 조회 시점에 결정).
    """
    period_year_map = {
        "thstrm_amount": base_year,
        "frmtrm_amount": base_year - 1,
        "bfefrmtrm_amount": base_year - 2,
    }

    rows = []
    for _, r in df.iterrows():
        for col, yr in period_year_map.items():
            if pd.notna(r[col]):
                rows.append({
                    "업종": industry,
                    "회사명": corp_name,
                    "연도": yr,
                    "계정": r["account_label"],
                    "금액": r[col],
                    "경고": r["warning"] if r["warning"] else "",
                })

    return pd.DataFrame(rows)
