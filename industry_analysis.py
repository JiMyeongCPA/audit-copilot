import pandas as pd

DB_PATH = "financial_database.csv"


def load_database():
    df = pd.read_csv(DB_PATH, encoding="utf-8-sig")
    df["경고"] = df["경고"].fillna("")
    return df


def _safe_ratio(pivot, new_col, numerator, denominator):
    """분자/분모 열이 둘 다 있을 때만 비율 계산 (없으면 건너뜀, 분모가 0이면 무한대 대신 결측치로 처리)"""
    if numerator in pivot.columns and denominator in pivot.columns:
        denom = pivot[denominator].replace(0, float("nan"))
        pivot[new_col] = pivot[numerator] / denom


def compute_company_ratios(db, include_contract_asset=False):
    """회사/연도별 각종 재무비율 계산

    include_contract_asset=True면 계약자산(미청구공사)을 매출채권에 더해서 계산함.
    (계약자산이 없는 회사는 0으로 처리되어 계산에 영향 없음)
    """
    pivot = db.pivot_table(
        index=["업종", "회사명", "연도"], columns="계정", values="금액", aggfunc="first"
    ).reset_index()

    if "계약자산" not in pivot.columns:
        pivot["계약자산"] = 0
    pivot["계약자산"] = pivot["계약자산"].fillna(0)

    effective_receivables = pivot["매출채권"]
    if include_contract_asset:
        effective_receivables = pivot["매출채권"] + pivot["계약자산"]

    # 분모가 0이면 무한대(inf) 대신 결측치로 처리 (_safe_ratio와 동일한 규칙).
    # 소형사 중 매출채권=0, 재고자산=0, 매출액=0인 경우가 있어 inf가 업종 평균/박스플롯을 오염시킴.
    receivables_safe = effective_receivables.replace(0, float("nan"))
    inventory_safe = pivot["재고자산"].replace(0, float("nan"))
    revenue_safe = pivot["매출액"].replace(0, float("nan"))

    pivot["매출채권회전율"] = pivot["매출액"] / receivables_safe
    pivot["재고자산회전율"] = pivot["매출원가"] / inventory_safe
    pivot["계약자산_존재"] = pivot["계약자산"] > 0

    # 매출채권 관련 추가 지표
    pivot["매출채권평균회수기간"] = effective_receivables / revenue_safe * 365
    pivot["매출채권매출액비율"] = effective_receivables / revenue_safe

    # 재고자산 관련 추가 지표
    _safe_ratio(pivot, "재고자산매출액비율", "재고자산", "매출액")

    # 계약자산 관련 추가 지표
    _safe_ratio(pivot, "계약자산매출액비율", "계약자산", "매출액")
    if "계약자산" in pivot.columns:
        pivot["계약자산매출채권비율"] = pivot["계약자산"] / pivot["매출채권"]

    # 유동성 지표
    _safe_ratio(pivot, "현금비율", "현금및현금성자산", "유동부채")
    _safe_ratio(pivot, "유동비율", "유동자산", "유동부채")
    if "유동자산" in pivot.columns and "재고자산" in pivot.columns and "유동부채" in pivot.columns:
        pivot["당좌비율"] = (pivot["유동자산"] - pivot["재고자산"]) / pivot["유동부채"]

    # 매입채무 회전율
    _safe_ratio(pivot, "매입채무회전율", "매출원가", "매입채무")

    # 레버리지 지표
    _safe_ratio(pivot, "부채비율", "부채총계", "자본총계")
    _safe_ratio(pivot, "총부채총자산", "부채총계", "자산총계")
    _safe_ratio(pivot, "장기차입금자산비율", "장기차입금", "자산총계")

    debt_cols = ["단기차입금", "유동성장기부채", "장기차입금"]
    for col in debt_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    debt_all_missing = pivot[debt_cols].isna().all(axis=1)
    pivot["총차입금"] = pivot[debt_cols].fillna(0).sum(axis=1)
    pivot.loc[debt_all_missing, "총차입금"] = float("nan")
    _safe_ratio(pivot, "차입금의존도", "총차입금", "자산총계")
    _safe_ratio(pivot, "금융원가차입금비율", "금융원가", "총차입금")

    # 수익성 지표
    _safe_ratio(pivot, "ROE", "당기순이익", "자본총계")
    _safe_ratio(pivot, "ROA", "당기순이익", "자산총계")
    _safe_ratio(pivot, "영업이익률", "영업이익", "매출액")
    _safe_ratio(pivot, "이자보상배율", "영업이익", "금융원가")
    _safe_ratio(pivot, "순이익률", "당기순이익", "매출액")

    # 매출액/매출원가/자산총계 관련 추가 지표
    _safe_ratio(pivot, "총자산회전율", "매출액", "자산총계")
    _safe_ratio(pivot, "매출원가율", "매출원가", "매출액")

    # 비유동자산 관련 지표 (2단계 확장)
    _safe_ratio(pivot, "유형자산회전율", "매출액", "유형자산")
    _safe_ratio(pivot, "유형자산총자산비율", "유형자산", "자산총계")
    _safe_ratio(pivot, "사용권자산총자산비율", "사용권자산", "자산총계")
    _safe_ratio(pivot, "무형자산총자산비율", "무형자산", "자산총계")
    _safe_ratio(pivot, "영업권총자산비율", "영업권", "자산총계")
    _safe_ratio(pivot, "투자부동산총자산비율", "투자부동산", "자산총계")
    _safe_ratio(pivot, "관계기업투자총자산비율", "관계기업투자", "자산총계")
    _safe_ratio(pivot, "이연법인세자산자본비율", "이연법인세자산", "자본총계")

    # 충당부채/계약부채 (2단계 확장)
    provision_cols = ["유동충당부채", "비유동충당부채"]
    for col in provision_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    provisions_all_missing = pivot[provision_cols].isna().all(axis=1)
    pivot["충당부채총계"] = pivot[provision_cols].fillna(0).sum(axis=1)
    pivot.loc[provisions_all_missing, "충당부채총계"] = float("nan")
    _safe_ratio(pivot, "충당부채매출액비율", "충당부채총계", "매출액")
    _safe_ratio(pivot, "계약부채매출액비율", "계약부채", "매출액")

    # 자본 항목 (2단계 확장)
    _safe_ratio(pivot, "자기주식자본비율", "자기주식", "자본총계")

    # 손익계산서 항목 (2단계 확장)
    _safe_ratio(pivot, "매출총이익률", "매출총이익", "매출액")
    _safe_ratio(pivot, "판관비율", "판매비와관리비", "매출액")
    _safe_ratio(pivot, "금융수익매출액비율", "금융수익", "매출액")
    _safe_ratio(pivot, "세전이익률", "법인세비용차감전순이익", "매출액")
    _safe_ratio(pivot, "유효세율", "법인세비용", "법인세비용차감전순이익")

    # 현금흐름표 항목 (3단계 확장)
    _safe_ratio(pivot, "OCF매출액비율", "영업활동현금흐름", "매출액")
    if "투자활동현금흐름" in pivot.columns and "매출액" in pivot.columns:
        pivot["투자현금흐름부담률"] = -pivot["투자활동현금흐름"] / pivot["매출액"].replace(0, float("nan"))
    _safe_ratio(pivot, "외부자금의존도", "재무활동현금흐름", "영업활동현금흐름")
    _safe_ratio(pivot, "현금세율", "법인세납부액", "법인세비용차감전순이익")
    _safe_ratio(pivot, "영업현금배당지급률", "배당금지급액", "영업활동현금흐름")

    capex_cols = ["유형자산취득액", "무형자산취득액"]
    for col in capex_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    capex_all_missing = pivot[capex_cols].isna().all(axis=1)
    pivot["CAPEX"] = pivot[capex_cols].fillna(0).sum(axis=1)
    pivot.loc[capex_all_missing, "CAPEX"] = float("nan")
    _safe_ratio(pivot, "CAPEX커버리지", "영업활동현금흐름", "CAPEX")

    disposal_cols = ["유형자산처분액", "무형자산처분액"]
    for col in disposal_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    disposal_all_missing = pivot[disposal_cols].isna().all(axis=1)
    pivot["자산처분액"] = pivot[disposal_cols].fillna(0).sum(axis=1)
    pivot.loc[disposal_all_missing, "자산처분액"] = float("nan")
    _safe_ratio(pivot, "자산처분현금비율", "자산처분액", "매출액")

    borrow_in_cols = ["단기차입금유입액", "장기차입금유입액"]
    for col in borrow_in_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    borrow_in_all_missing = pivot[borrow_in_cols].isna().all(axis=1)
    pivot["차입금유입액"] = pivot[borrow_in_cols].fillna(0).sum(axis=1)
    pivot.loc[borrow_in_all_missing, "차입금유입액"] = float("nan")

    borrow_out_cols = ["단기차입금상환액", "장기차입금상환액"]
    for col in borrow_out_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    borrow_out_all_missing = pivot[borrow_out_cols].isna().all(axis=1)
    pivot["차입금상환액"] = pivot[borrow_out_cols].fillna(0).sum(axis=1)
    pivot.loc[borrow_out_all_missing, "차입금상환액"] = float("nan")

    lease_cols = ["유동리스부채", "비유동리스부채"]
    for col in lease_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    lease_all_missing = pivot[lease_cols].isna().all(axis=1)
    pivot["리스부채"] = pivot[lease_cols].fillna(0).sum(axis=1)
    pivot.loc[lease_all_missing, "리스부채"] = float("nan")

    # 평균잔액이 필요한 비율(신규차입률/차입금상환률/현금이자율/리스부채상환률)은
    # 같은 회사 내에서 연도순으로 전기 잔액을 가져와야 하므로 정렬 후 계산
    pivot = pivot.sort_values(["회사명", "연도"])
    pivot["총차입금_전기"] = pivot.groupby("회사명")["총차입금"].shift(1)
    pivot["평균차입금"] = (pivot["총차입금"] + pivot["총차입금_전기"]) / 2
    _safe_ratio(pivot, "신규차입률", "차입금유입액", "평균차입금")
    _safe_ratio(pivot, "차입금상환률", "차입금상환액", "평균차입금")
    _safe_ratio(pivot, "현금이자율", "이자지급액", "평균차입금")

    if "리스부채" in pivot.columns:
        pivot["리스부채_전기"] = pivot.groupby("회사명")["리스부채"].shift(1)
        pivot["평균리스부채"] = (pivot["리스부채"] + pivot["리스부채_전기"]) / 2
        _safe_ratio(pivot, "리스부채상환률", "리스부채상환액", "평균리스부채")

    warn = db[(db["계정"] == "매출채권") & (db["경고"] != "")][["회사명"]].drop_duplicates()
    warn["매출채권_경고있음"] = True
    pivot = pivot.merge(warn, on="회사명", how="left")
    pivot["매출채권_경고있음"] = pivot["매출채권_경고있음"].fillna(False)

    return pivot


def compute_industry_average(ratios_df, industry, year, ratio_col):
    """업종 대표값 = 그 업종 회사들의 비율 '중앙값'

    산술평균 대신 중앙값을 쓰는 이유: 소형사 중 분모가 아주 작은 회사(재고자산·매출채권이
    거의 0)가 회전율 같은 지표에서 수천 배의 극단값을 만들어, 산술평균이면 업종 대표값이
    비현실적으로 커짐(예: 건설업 재고자산회전율 92회, IT 5356회). 중앙값은 이런 극단값에
    강건하고 박스플롯의 중앙선과도 일치함.

    매출채권평균회수기간은 매출채권회전율의 역수라서, 두 지표를 각각 따로 요약하면
    365/(회전율 대표값)과 (회수기간 대표값)이 수학적으로 안 맞음(젠센 부등식). 그래서
    회수기간은 "365 / 업종 중앙값 회전율"로 역산해서, 화면에 같이 뜨는 두 지표가 항상 일치하게 함.
    """
    subset = ratios_df[(ratios_df["업종"] == industry) & (ratios_df["연도"] == year)]

    if ratio_col == "매출채권평균회수기간":
        turnover_median = subset["매출채권회전율"].median()
        if pd.isna(turnover_median) or turnover_median == 0:
            return None
        return 365 / turnover_median

    if ratio_col not in subset.columns:
        return None
    value = subset[ratio_col].median()
    return value if pd.notna(value) else None


def _boxplot_stats_from_values(values, company_value):
    q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr

    is_outlier = company_value is not None and pd.notna(company_value) and (
        company_value < lower_fence or company_value > upper_fence
    )

    return {
        "q1": round(q1, 2),
        "median": round(median, 2),
        "q3": round(q3, 2),
        "min": round(values.min(), 2),
        "max": round(values.max(), 2),
        "company_value": round(company_value, 2) if company_value is not None and pd.notna(company_value) else None,
        "is_outlier": is_outlier,
        "표본수": len(values),
    }


def compute_boxplot_stats(ratios_df, industry, year, ratio_col, corp_name):
    """업종 내 비율 분포의 사분위수 + 선택 회사가 이상치인지 여부 (IQR 1.5배 기준)"""
    subset = ratios_df[(ratios_df["업종"] == industry) & (ratios_df["연도"] == year)]
    values = subset[ratio_col].dropna()

    company_row = subset[subset["회사명"] == corp_name]
    company_value = company_row.iloc[0][ratio_col] if not company_row.empty else None

    return _boxplot_stats_from_values(values, company_value)


def compute_growth_boxplot_stats(growth_series, corp_name):
    """계정 금액 증감률(%) Series에 대한 사분위수 + 이상치 여부 (IQR 1.5배 기준)"""
    values = growth_series.dropna()
    company_value = growth_series.get(corp_name)
    return _boxplot_stats_from_values(values, company_value)
