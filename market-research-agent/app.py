import os

import streamlit as st
from dotenv import load_dotenv

from graph import build_graph

load_dotenv()

st.set_page_config(page_title="Market Research Agent", layout="wide")
st.title("Market Research Agent")

company_name = st.text_input("Company / Product Name")

if st.button("Run Research Pipeline"):
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is not set. Add it to your .env file.")
        st.stop()
    if not company_name:
        st.warning("Enter a company or product name.")
        st.stop()

    graph = build_graph()

    with st.status(f"Researching competitors for {company_name}...", expanded=True) as status:
        st.write("Discovering top competitors...")
        result = graph.invoke({
            "company": company_name,
            "competitor_queue": [],
            "final_reports": [],
        })
        st.write(f"Compiled {len(result['final_reports'])} competitor reports.")
        status.update(label="Research complete", state="complete")

    for report in result["final_reports"]:
        with st.expander(f"📦 {report['competitor_name']}"):
            left, right = st.columns(2)
            with left:
                st.markdown("**Pricing Model**")
                st.write(report["pricing_model"])
                st.markdown("**Market Positioning**")
                st.write(report["market_positioning"])
            with right:
                st.markdown("**Core Features**")
                for feature in report["core_features"]:
                    st.markdown(f"- {feature}")
                st.markdown("**Recent News**")
                st.write(report["recent_news"])
