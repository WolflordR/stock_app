import pandas as pd
import streamlit as st


def render_chain_reaction_tab():
    st.write("**痛點連鎖反應模型**")
    st.caption("看到第一層爆發時，不要只追第一層，往後推演下一個會短缺、會卡關、會漲價的是誰。")

    chain_df = pd.DataFrame(
        [
            {"層級": "第一層｜算力", "痛點 / 需求": "GPU 需求爆發", "對應台股方向": "CoWoS / 先進封裝、載板、ASIC"},
            {"層級": "第二層｜傳輸", "痛點 / 需求": "傳輸速度不夠", "對應台股方向": "矽光子、CPO、光通訊、交換器"},
            {"層級": "第三層｜散熱", "痛點 / 需求": "功耗與熱密度暴增", "對應台股方向": "液冷、散熱模組、伺服器機殼"},
            {"層級": "第四層｜基礎設施", "痛點 / 需求": "資料中心耗電上升", "對應台股方向": "重電、電源管理、BBU、儲能"},
        ]
    )
    st.dataframe(chain_df, use_container_width=True, hide_index=True)

    note_cols = st.columns(2)
    with note_cols[0]:
        st.write("**今天先從哪個痛點開始推？**")
        st.text_area(
            "研究筆記",
            value="例如：微軟 Capex 持續加大，下一個瓶頸可能從光通訊轉向電力與散熱。",
            height=120,
            key="research_chain_note",
        )
    with note_cols[1]:
        st.write("**下一步要埋伏哪一層？**")
        st.text_area(
            "埋伏方向",
            value="例如：先不追 GPU，改看 CPO / 矽光子、液冷、BBU。",
            height=120,
            key="research_chain_followup",
        )
