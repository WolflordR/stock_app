import streamlit as st

from research_page_candidates import render_research_candidate_tab


def render_research_page(state):
    st.subheader("研究工作台")
    st.caption("先把研究流程收斂成單一的起漲候選工作區，避免頁面太雜。")
    render_research_candidate_tab(state)
