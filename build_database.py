import time
import pandas as pd
from dart_client import get_account_data, to_long_format

COMPANIES = {
    "반도체/전자부품": [
        "삼성전자", "SK하이닉스", "DB하이텍", "삼성전기", "LG이노텍",
        "원익QnC", "원익IPS", "하나마이크론", "ISC", "LX세미콘",
    ],
    "건설업": [
        "현대건설", "GS건설", "대우건설", "DL이앤씨", "한신공영",
        "서희건설", "코오롱글로벌", "아이에스동서", "신세계건설", "삼부토건",
    ],
    "유통업": [
        "이마트", "롯데쇼핑", "GS리테일", "BGF리테일", "현대백화점",
        "신세계인터내셔날", "현대홈쇼핑", "한섬", "F&F", "CJ프레시웨이",
    ],
    "자동차": [
        "현대자동차", "HL만도", "현대모비스", "한국타이어앤테크놀로지", "성우하이텍",
        "인지컨트롤스", "현대위아", "넥센타이어", "평화홀딩스", "대원강업",
    ],
    "화학": [
        "LG화학", "롯데케미칼", "금호석유화학", "한화솔루션", "SK이노베이션",
        "한솔케미칼", "OCI홀딩스", "애경케미칼", "남해화학", "SKC",
    ],
    "철강": [
        "POSCO홀딩스", "현대제철", "동국씨엠", "세아베스틸지주", "KG스틸",
        "대한제강", "휴스틸", "대양금속", "세아제강", "세아특수강",
    ],
    "제약/바이오": [
        "삼성바이오로직스", "SK바이오사이언스", "유한양행", "종근당", "한미약품",
        "대웅제약", "녹십자", "동아에스티", "일동제약", "보령",
    ],
    "식품": [
        "CJ제일제당", "오뚜기", "농심", "롯데웰푸드", "삼양식품",
        "매일유업", "대상", "하이트진로", "동원F&B", "풀무원",
    ],
    "해운/운송": [
        "HMM", "팬오션", "대한항공", "아시아나항공", "CJ대한통운",
        "세방", "KSS해운", "흥아해운", "현대글로비스", "한진칼",
    ],
    "IT서비스": [
        "삼성에스디에스", "NAVER", "더존비즈온", "안랩", "한글과컴퓨터",
        "다우기술", "케이아이엔엑스", "오픈베이스", "인성정보", "비트컴퓨터",
    ],
}

YEAR = 2025

all_rows = []
errors = []

for industry, companies in COMPANIES.items():
    for corp in companies:
        try:
            df = get_account_data(corp, YEAR)
            if df.empty:
                errors.append(f"{corp}: 계정 데이터 없음 (account_id 매칭 실패)")
                continue
            long_df = to_long_format(df, corp, industry, YEAR)
            all_rows.append(long_df)
            print(f"완료: {industry} - {corp} ({len(long_df)}행)")
        except Exception as e:
            errors.append(f"{corp}: {e}")
        time.sleep(0.3)

result = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
result.to_csv("financial_database.csv", index=False, encoding="utf-8-sig")
print(f"\n총 {len(result)}행 저장 완료 -> financial_database.csv")

if errors:
    print("\n=== 에러/누락 ===")
    for e in errors:
        print(e)
