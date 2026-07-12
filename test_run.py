from dart_client import get_account_data, compute_turnover_ratios

df = get_account_data("삼성전자", 2024)
print("=== 뽑힌 계정 데이터 ===")
print(df.to_string())

print("\n=== 회전율 계산 결과 ===")
for row in compute_turnover_ratios(df):
    print(row)
