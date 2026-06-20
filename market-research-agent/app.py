import os

import streamlit as st
from dotenv import load_dotenv

from graph import build_graph

load_dotenv()

st.set_page_config(page_title="Market Research Agent", layout="wide")
st.title("Market Research Agent")


def render_full_report(report: dict, company_name: str) -> None:
    competitor_name = report["competitor_name"]

    st.markdown("##### Source Quality")
    if report["sources"]:
        st.dataframe(
            [
                {
                    "Title": s["title"],
                    "Type": s["source_type"],
                    "Favors": s["favors"],
                    "Evidence": s["evidence_quality"],
                    "Bias Risk": s["bias_risk"],
                    "Insight": s["insight"],
                }
                for s in report["sources"]
            ],
            use_container_width=True,
        )
    else:
        st.write("No sources captured.")

    st.markdown("##### Positioning")
    pos = report["positioning"]
    left, right = st.columns(2)
    with left:
        st.markdown(f"**{company_name}**")
        st.write(f"Problem solved: {pos['company_problem_solved']}")
        st.write(f"Promise: {pos['company_promise']}")
        st.write(f"Segment: {pos['company_segment']}")
    with right:
        st.markdown(f"**{competitor_name}**")
        st.write(f"Problem solved: {pos['competitor_problem_solved']}")
        st.write(f"Promise: {pos['competitor_promise']}")
        st.write(f"Segment: {pos['competitor_segment']}")
    st.caption(pos["positioning_difference"])

    st.markdown("##### Feature Comparison")
    if report["feature_comparison"]:
        st.dataframe(
            [
                {
                    "Dimension": f["dimension"],
                    company_name: f["company_value"],
                    competitor_name: f["competitor_value"],
                    "PM Interpretation": f["pm_interpretation"],
                }
                for f in report["feature_comparison"]
            ],
            use_container_width=True,
        )

    st.markdown("##### Customer Perception")
    perception = report["customer_perception"]
    left, right = st.columns(2)
    with left:
        st.markdown(f"**{company_name} praise**")
        for item in perception["company_praise"]:
            st.markdown(f"- {item}")
        st.markdown(f"**{company_name} complaints**")
        for item in perception["company_complaints"]:
            st.markdown(f"- {item}")
    with right:
        st.markdown(f"**{competitor_name} praise**")
        for item in perception["competitor_praise"]:
            st.markdown(f"- {item}")
        st.markdown(f"**{competitor_name} complaints**")
        for item in perception["competitor_complaints"]:
            st.markdown(f"- {item}")

    st.markdown("##### Pricing / Packaging")
    pricing = report["pricing"]
    st.write(pricing["packaging_notes"])
    st.write(pricing["pricing_complaints"])

    st.markdown("##### Strategic Read")
    strategic = report["strategic_read"]
    st.write(f"Competitor's market belief: {strategic['competitor_market_belief']}")
    st.write(f"Expectation being shaped: {strategic['expectation_being_shaped']}")
    st.write(f"{company_name} vulnerability: {strategic['company_vulnerability']}")
    st.write(f"{company_name} advantage: {strategic['company_advantage']}")
    st.write(f"Watch (6-12 months): {strategic['watch_next_6_12_months']}")

    st.markdown("##### PM Recommendations")
    recs = report["recommendations"]
    for label, key in [
        ("Do now", "do_now"),
        ("Do not blindly copy", "do_not_blindly_copy"),
        ("Watch", "watch"),
    ]:
        st.markdown(f"**{label}**")
        for rec in recs[key]:
            st.markdown(f"- {rec['action']} (confidence: {rec['confidence']}) — {rec['rationale']}")

    st.markdown("##### Open Questions")
    for question in report["open_questions"]:
        st.markdown(f"- {question}")


def report_to_markdown(report: dict, company_name: str) -> str:
    competitor_name = report["competitor_name"]
    lines = [f"## {competitor_name}", "", report["executive_summary"], ""]

    lines.append("### Source Quality")
    if report["sources"]:
        lines.append("| Title | Type | Favors | Evidence | Bias Risk | Insight |")
        lines.append("|---|---|---|---|---|---|")
        for s in report["sources"]:
            lines.append(
                f"| {s['title']} | {s['source_type']} | {s['favors']} | "
                f"{s['evidence_quality']} | {s['bias_risk']} | {s['insight']} |"
            )
    else:
        lines.append("No sources captured.")
    lines.append("")

    pos = report["positioning"]
    lines.append("### Positioning")
    lines.append(
        f"- **{company_name}** — Problem solved: {pos['company_problem_solved']}; "
        f"Promise: {pos['company_promise']}; Segment: {pos['company_segment']}"
    )
    lines.append(
        f"- **{competitor_name}** — Problem solved: {pos['competitor_problem_solved']}; "
        f"Promise: {pos['competitor_promise']}; Segment: {pos['competitor_segment']}"
    )
    lines.append(f"*{pos['positioning_difference']}*")
    lines.append("")

    lines.append("### Feature Comparison")
    if report["feature_comparison"]:
        lines.append(f"| Dimension | {company_name} | {competitor_name} | PM Interpretation |")
        lines.append("|---|---|---|---|")
        for f in report["feature_comparison"]:
            lines.append(
                f"| {f['dimension']} | {f['company_value']} | {f['competitor_value']} | "
                f"{f['pm_interpretation']} |"
            )
    lines.append("")

    perception = report["customer_perception"]
    lines.append("### Customer Perception")
    lines.append(f"- **{company_name} praise:** " + "; ".join(perception["company_praise"]))
    lines.append(
        f"- **{company_name} complaints:** " + "; ".join(perception["company_complaints"])
    )
    lines.append(
        f"- **{competitor_name} praise:** " + "; ".join(perception["competitor_praise"])
    )
    lines.append(
        f"- **{competitor_name} complaints:** "
        + "; ".join(perception["competitor_complaints"])
    )
    lines.append("")

    pricing = report["pricing"]
    lines.append("### Pricing / Packaging")
    lines.append(f"- Summary: {pricing['summary']}")
    lines.append(f"- Packaging: {pricing['packaging_notes']}")
    lines.append(f"- Complaints: {pricing['pricing_complaints']}")
    lines.append("")

    strategic = report["strategic_read"]
    lines.append("### Strategic Read")
    lines.append(f"- Competitor's market belief: {strategic['competitor_market_belief']}")
    lines.append(f"- Expectation being shaped: {strategic['expectation_being_shaped']}")
    lines.append(f"- {company_name} vulnerability: {strategic['company_vulnerability']}")
    lines.append(f"- {company_name} advantage: {strategic['company_advantage']}")
    lines.append(f"- Watch (6-12 months): {strategic['watch_next_6_12_months']}")
    lines.append("")

    lines.append("### PM Recommendations")
    recs = report["recommendations"]
    for label, key in [
        ("Do now", "do_now"),
        ("Do not blindly copy", "do_not_blindly_copy"),
        ("Watch", "watch"),
    ]:
        lines.append(f"**{label}**")
        for rec in recs[key]:
            lines.append(f"- {rec['action']} (confidence: {rec['confidence']}) — {rec['rationale']}")
    lines.append("")

    lines.append("### Open Questions")
    for question in report["open_questions"]:
        lines.append(f"- {question}")
    lines.append("")

    return "\n".join(lines)


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

    st.session_state["result"] = result
    st.session_state["company_name"] = company_name

if "result" in st.session_state:
    result = st.session_state["result"]
    company_name = st.session_state["company_name"]
    reports = result["final_reports"]

    st.markdown("### Executive Summary")
    st.write(result["overall_summary"])

    full_markdown = (
        f"# Competitive Analysis: {company_name}\n\n"
        f"## Executive Summary\n\n{result['overall_summary']}\n\n"
        + "\n".join(report_to_markdown(r, company_name) for r in reports)
    )
    st.download_button(
        label="Download Full Report",
        data=full_markdown,
        file_name=f"{company_name.replace(' ', '_')}_competitive_analysis.md",
        mime="text/markdown",
    )

    columns = st.columns(len(reports))
    for column, report in zip(columns, reports):
        with column:
            with st.container(border=True):
                st.markdown(f"#### 📦 {report['competitor_name']}")
                st.write(report["executive_summary"])
                st.markdown(f"💰 **Pricing:** {report['pricing']['summary']}")
                st.caption(report["positioning"]["positioning_difference"])

                with st.expander("Full report"):
                    render_full_report(report, company_name)
