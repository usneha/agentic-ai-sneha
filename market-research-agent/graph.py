import operator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, List, TypedDict

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from models import CompetitorList, CompetitorReport, SlideDeck

web_search = DuckDuckGoSearchRun()
deep_search = DuckDuckGoSearchAPIWrapper(max_results=4)

RESEARCH_QUERIES = [
    ("Direct comparison", "{competitor} vs {company}"),
    ("Alternatives", "{competitor} alternatives {company}"),
    ("Switching language", "why switch from {company} to {competitor}"),
    ("Customer complaints", "{competitor} customer complaints"),
    ("Recent news", "{competitor} vs {company} news announcement 2026"),
]

DISCOVERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a market research analyst."),
    (
        "human",
        "Top 3 specific product competitors to {company}. Do not include "
        "{company} itself in the list.\n\n"
        "Search results:\n{raw_data}",
    ),
])

ANALYST_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a market research agent for a product manager, researching how "
        "{company} compares against {competitor}. Produce grounded, decision-useful "
        "competitor intelligence, not a generic company overview: what customers are "
        "comparing, why they choose one over the other, where each is perceived as "
        "stronger or weaker, and the strategic implications for {company}.\n\n"
        "Separate observed evidence from your own interpretation. For each source you "
        "cite, judge its evidence quality and bias risk; do not treat vendor pages or "
        "affiliate/SEO comparison fluff as neutral evidence, and do not present "
        "competitor marketing claims as objective truth. If sources disagree, say so. "
        "Do not hallucinate; write 'Not found' for any field unsupported by the search "
        "results below. Be concise: every field has a maximum length or list size noted "
        "in its schema description, and you must stay within those limits.",
    ),
    ("human", "Search results:\n{raw_data}"),
])

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a market research agent for a product manager. You have already "
        "researched how {company} compares against {count} competitors. Write a "
        "single executive summary (3-5 sentences) synthesizing the overall "
        "competitive landscape: the clearest pattern across competitors, where "
        "{company} is consistently stronger or weaker, what customers seem to value "
        "most in this category, and the biggest strategic implication for a PM. "
        "Do not just repeat each competitor's summary one by one; synthesize.",
    ),
    ("human", "Per-competitor findings:\n{competitor_summaries}"),
])

DECK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a strategy consultant and product strategy advisor creating a "
        "McKinsey-style executive slide deck from a completed competitive analysis "
        "comparing {company} against its competitive set in this category. Your "
        "goal is not to summarize every finding; it is a clear strategic narrative "
        "that helps leaders decide where competitors are winning, where {company} "
        "is vulnerable, where it has a right to win, what to do now, what not to "
        "blindly copy, and what to monitor.\n\n"
        "McKinsey style: one slide makes one argument; slide titles are full-"
        "sentence insights, not topic labels (bad: 'Feature Comparison'; good: "
        "'Competitors are winning on ease of adoption, but depth remains limited'); "
        "every slide answers 'so what'; use evidence, not generic claims; separate "
        "fact from interpretation; avoid clutter, marketing language, and "
        "unsupported recommendations. Since there are multiple competitors, slides "
        "that would normally compare two products (positioning, product/experience, "
        "vulnerabilities, differentiation) should synthesize across the whole "
        "competitive set, not pick just one rival.\n\n"
        "Produce 8 to 12 slides following this default storyline unless the input "
        "strongly suggests otherwise: (1) executive takeaway, (2) market context "
        "and customer job, (3) positioning comparison across the set, (4) customer "
        "decision drivers, (5) product/experience comparison, (6) competitive "
        "vulnerabilities, (7) differentiation opportunities, (8) strategic options "
        "(2-4 options as a table: description, customer impact, business impact, "
        "effort, risk, evidence strength, when it applies), (9) recommendation, "
        "(10) roadmap (do now / do not blindly copy / watch), (11) risks and "
        "unknowns, (12) appendix: source quality. Slide titles read together "
        "should form one storyline.\n\n"
        "Do not invent facts; use only the competitive analysis provided below. If "
        "evidence is weak, say so explicitly rather than overstating confidence.",
    ),
    ("human", "Competitive analysis:\n{competitive_analysis}"),
])


class ResearchState(TypedDict):
    company: str
    competitor_queue: List[str]
    current_target: str
    raw_data: str
    final_reports: Annotated[List[dict], operator.add]
    overall_summary: str
    deck: dict


def _llm(model: str = "gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=0)


def _format_results(label: str, results: list) -> str:
    lines = [f"--- {label} ---"]
    for r in results:
        lines.append(
            f"Title: {r.get('title', 'Untitled')}\n"
            f"URL: {r.get('link', 'Not found')}\n"
            f"Snippet: {r.get('snippet', '')}"
        )
    return "\n".join(lines)


def discovery_node(state: ResearchState) -> dict:
    raw_data = web_search.invoke(
        f"Top 3 specific product competitors to {state['company']} software"
    )
    structured_llm = _llm().with_structured_output(CompetitorList)
    chain = DISCOVERY_PROMPT | structured_llm
    result: CompetitorList = chain.invoke({"company": state["company"], "raw_data": raw_data})
    competitors = [
        c for c in result.competitors if c.strip().lower() != state["company"].strip().lower()
    ]
    return {"competitor_queue": competitors[:3]}


def researcher_node(state: ResearchState) -> dict:
    queue = list(state["competitor_queue"])
    competitor = queue.pop(0)
    company = state["company"]

    with ThreadPoolExecutor(max_workers=len(RESEARCH_QUERIES)) as executor:
        futures = {
            label: executor.submit(
                deep_search.results,
                template.format(competitor=competitor, company=company),
                4,
            )
            for label, template in RESEARCH_QUERIES
        }
        sections = [_format_results(label, future.result()) for label, future in futures.items()]

    raw_data = "\n\n".join(sections)
    return {
        "competitor_queue": queue,
        "current_target": competitor,
        "raw_data": raw_data,
    }


def analyst_node(state: ResearchState) -> dict:
    structured_llm = _llm("gpt-4.1-mini").with_structured_output(CompetitorReport)
    chain = ANALYST_PROMPT | structured_llm
    report: CompetitorReport = chain.invoke({
        "competitor": state["current_target"],
        "company": state["company"],
        "raw_data": state["raw_data"],
    })
    return {"final_reports": [report.model_dump()]}


def summary_node(state: ResearchState) -> dict:
    competitor_summaries = "\n\n".join(
        f"{r['competitor_name']}: {r['executive_summary']} "
        f"(Pricing: {r['pricing']['summary']})"
        for r in state["final_reports"]
    )
    chain = SUMMARY_PROMPT | _llm("gpt-4.1-mini")
    response = chain.invoke({
        "company": state["company"],
        "count": len(state["final_reports"]),
        "competitor_summaries": competitor_summaries,
    })
    return {"overall_summary": response.content}


def _format_competitive_analysis(company: str, overall_summary: str, reports: list) -> str:
    sections = [f"Company: {company}", f"Overall executive summary: {overall_summary}"]
    for r in reports:
        pos = r["positioning"]
        perception = r["customer_perception"]
        pricing = r["pricing"]
        strategic = r["strategic_read"]
        sections.append(
            f"\n--- Competitor: {r['competitor_name']} ---\n"
            f"Executive summary: {r['executive_summary']}\n"
            f"Sources: "
            + "; ".join(
                f"{s['title']} ({s['url']}, evidence={s['evidence_quality']}, "
                f"bias={s['bias_risk']}, favors={s['favors']}): {s['insight']}"
                for s in r["sources"]
            )
            + f"\nPositioning - {company}: {pos['company_problem_solved']} / "
            f"{pos['company_promise']} / {pos['company_segment']}\n"
            f"Positioning - {r['competitor_name']}: {pos['competitor_problem_solved']} / "
            f"{pos['competitor_promise']} / {pos['competitor_segment']}\n"
            f"Positioning difference: {pos['positioning_difference']}\n"
            f"Feature comparison: "
            + "; ".join(
                f"{f['dimension']}: {company}={f['company_value']} vs "
                f"{r['competitor_name']}={f['competitor_value']} ({f['pm_interpretation']})"
                for f in r["feature_comparison"]
            )
            + f"\nCustomer praise ({company}): {'; '.join(perception['company_praise'])}\n"
            f"Customer complaints ({company}): {'; '.join(perception['company_complaints'])}\n"
            f"Customer praise ({r['competitor_name']}): "
            f"{'; '.join(perception['competitor_praise'])}\n"
            f"Customer complaints ({r['competitor_name']}): "
            f"{'; '.join(perception['competitor_complaints'])}\n"
            f"Pricing: {pricing['summary']} | {pricing['packaging_notes']} | "
            f"{pricing['pricing_complaints']}\n"
            f"Strategic read: belief={strategic['competitor_market_belief']}; "
            f"expectation={strategic['expectation_being_shaped']}; "
            f"vulnerability={strategic['company_vulnerability']}; "
            f"advantage={strategic['company_advantage']}; "
            f"watch={strategic['watch_next_6_12_months']}\n"
            f"Open questions: {'; '.join(r['open_questions'])}"
        )
    return "\n".join(sections)


def deck_node(state: ResearchState) -> dict:
    competitive_analysis = _format_competitive_analysis(
        state["company"], state["overall_summary"], state["final_reports"]
    )
    structured_llm = _llm("gpt-4.1-mini").with_structured_output(SlideDeck)
    chain = DECK_PROMPT | structured_llm
    deck: SlideDeck = chain.invoke({
        "company": state["company"],
        "competitive_analysis": competitive_analysis,
    })
    return {"deck": deck.model_dump()}


def queue_router(state: ResearchState):
    if len(state["competitor_queue"]) == 0:
        return "Summary"
    return "Researcher"


def build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("Discovery", discovery_node)
    graph.add_node("Researcher", researcher_node)
    graph.add_node("Analyst", analyst_node)
    graph.add_node("Summary", summary_node)
    graph.add_node("Deck", deck_node)

    graph.add_edge(START, "Discovery")
    graph.add_edge("Discovery", "Researcher")
    graph.add_edge("Researcher", "Analyst")
    graph.add_conditional_edges("Analyst", queue_router)
    graph.add_edge("Summary", "Deck")
    graph.add_edge("Deck", END)

    return graph.compile()
