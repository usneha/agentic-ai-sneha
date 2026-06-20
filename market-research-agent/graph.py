import operator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, List, TypedDict

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from models import CompetitorList, CompetitorReport

web_search = DuckDuckGoSearchRun()

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
        "You are an elite market analyst comparing {competitor} against {company}. "
        "Do not hallucinate; write 'Data not found' for any field you cannot "
        "support from the search results below.",
    ),
    ("human", "Search results:\n{raw_data}"),
])


class ResearchState(TypedDict):
    company: str
    competitor_queue: List[str]
    current_target: str
    raw_data: str
    final_reports: Annotated[List[dict], operator.add]


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


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

    with ThreadPoolExecutor(max_workers=2) as executor:
        overview_future = executor.submit(
            web_search.invoke,
            f"{competitor} software pricing features market positioning vs {company}",
        )
        news_future = executor.submit(
            web_search.invoke, f"{competitor} vs {company} news announcement 2026"
        )
        overview_data = overview_future.result()
        news_data = news_future.result()

    raw_data = f"{overview_data}\n\n--- NEWS ---\n{news_data}"
    return {
        "competitor_queue": queue,
        "current_target": competitor,
        "raw_data": raw_data,
    }


def analyst_node(state: ResearchState) -> dict:
    structured_llm = _llm().with_structured_output(CompetitorReport)
    chain = ANALYST_PROMPT | structured_llm
    report: CompetitorReport = chain.invoke({
        "competitor": state["current_target"],
        "company": state["company"],
        "raw_data": state["raw_data"],
    })
    return {"final_reports": [report.model_dump()]}


def queue_router(state: ResearchState):
    if len(state["competitor_queue"]) == 0:
        return END
    return "Researcher"


def build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("Discovery", discovery_node)
    graph.add_node("Researcher", researcher_node)
    graph.add_node("Analyst", analyst_node)

    graph.add_edge(START, "Discovery")
    graph.add_edge("Discovery", "Researcher")
    graph.add_edge("Researcher", "Analyst")
    graph.add_conditional_edges("Analyst", queue_router)

    return graph.compile()
