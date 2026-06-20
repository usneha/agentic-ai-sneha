import operator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, List, TypedDict

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from models import CompetitorList, CompetitorReport

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


class ResearchState(TypedDict):
    company: str
    competitor_queue: List[str]
    current_target: str
    raw_data: str
    final_reports: Annotated[List[dict], operator.add]
    overall_summary: str


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

    graph.add_edge(START, "Discovery")
    graph.add_edge("Discovery", "Researcher")
    graph.add_edge("Researcher", "Analyst")
    graph.add_conditional_edges("Analyst", queue_router)
    graph.add_edge("Summary", END)

    return graph.compile()
