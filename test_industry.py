from industry_analysis import load_database, compute_company_ratios, compare_company_to_industry

db = load_database()

for include in [False, True]:
    print(f"\n########## 계약자산 포함 여부 = {include} ##########")
    ratios = compute_company_ratios(db, include_contract_asset=include)

    print("=== 회사별 회전율 (2024) ===")
    print(ratios[ratios["연도"] == 2024][
        ["업종", "회사명", "매출채권회전율", "재고자산회전율", "계약자산_존재"]
    ].to_string())

    print("\n=== GS건설 vs 업종 평균 (2024) ===")
    print(compare_company_to_industry(ratios, "GS건설", 2024))
