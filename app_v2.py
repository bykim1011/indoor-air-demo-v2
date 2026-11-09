
# -*- coding: utf-8 -*-
# 도원센트럴어린이집 공개용 공기질 안내서비스

import streamlit as st
from kweather_iaq240 import render_childcare_page

st.set_page_config(
    page_title="도원센트럴어린이집 공기질 안내",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

render_childcare_page()
