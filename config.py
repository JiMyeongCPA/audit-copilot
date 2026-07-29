import streamlit as st

# API 키 등 실제 비밀값만 secrets에서 읽음
API_KEY = st.secrets["API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# 모델명은 비밀이 아니므로 코드에서 관리(버전관리·변경 용이).
# 모델을 바꾸려면 아래 값만 수정하고 push하면 됨. (대시보드 secrets의 GEMINI_MODEL은 더 이상 사용하지 않음)
GEMINI_MODEL = "gemini-2.5-flash"
