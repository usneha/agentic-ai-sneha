from typing import List

from pydantic import BaseModel, Field

SENTENCE = "Max 1-2 sentences."
PHRASE = "Max ~15 words."


class CompetitorList(BaseModel):
    competitors: List[str] = Field(
        description="Exactly 3 specific competitor products or services."
    )


class SourceSummary(BaseModel):
    title: str
    url: str = Field(description="Source URL, or 'Not found' if unavailable")
    source_type: str = Field(
        description="e.g. comparison article, alternatives page, review site, "
        f"forum/community, vendor page, case study. {PHRASE}"
    )
    favors: str = Field(description="Which company this source favors, or 'Neutral'")
    evidence_quality: str = Field(description="High, Medium, or Low")
    bias_risk: str = Field(description="Low, Medium, or High")
    insight: str = Field(description=f"Key claim or quote from this source, paraphrased. {SENTENCE}")


class PositioningComparison(BaseModel):
    company_problem_solved: str = Field(description=PHRASE)
    company_promise: str = Field(description=PHRASE)
    company_segment: str = Field(description=PHRASE)
    competitor_problem_solved: str = Field(description=PHRASE)
    competitor_promise: str = Field(description=PHRASE)
    competitor_segment: str = Field(description=PHRASE)
    positioning_difference: str = Field(
        description=f"One-sentence summary of the positioning difference. {SENTENCE}"
    )


class FeatureRow(BaseModel):
    dimension: str = Field(description=PHRASE)
    company_value: str = Field(description=PHRASE)
    competitor_value: str = Field(description=PHRASE)
    pm_interpretation: str = Field(description=SENTENCE)


class CustomerPerception(BaseModel):
    company_praise: List[str] = Field(description=f"At most 3 items. {PHRASE} each.")
    company_complaints: List[str] = Field(description=f"At most 3 items. {PHRASE} each.")
    competitor_praise: List[str] = Field(description=f"At most 3 items. {PHRASE} each.")
    competitor_complaints: List[str] = Field(description=f"At most 3 items. {PHRASE} each.")


class PricingComparison(BaseModel):
    summary: str = Field(
        description=f"Which is cheaper/simpler/more flexible, or 'Not found'. {SENTENCE}"
    )
    packaging_notes: str = Field(
        description=f"Free tiers, trials, bundles, add-ons, usage-based pricing. {SENTENCE}"
    )
    pricing_complaints: str = Field(
        description=f"Customer complaints about pricing, or 'Not found'. {SENTENCE}"
    )


class StrategicRead(BaseModel):
    competitor_market_belief: str = Field(
        description=f"What the competitor seems to believe about where the market is "
        f"going. {SENTENCE}"
    )
    expectation_being_shaped: str = Field(description=SENTENCE)
    company_vulnerability: str = Field(description=SENTENCE)
    company_advantage: str = Field(description=SENTENCE)
    watch_next_6_12_months: str = Field(description=SENTENCE)


class Recommendation(BaseModel):
    action: str = Field(description=PHRASE)
    rationale: str = Field(description=SENTENCE)
    confidence: str = Field(description="High, Medium, or Low")


class Recommendations(BaseModel):
    do_now: List[Recommendation] = Field(description="At most 2 items")
    do_not_blindly_copy: List[Recommendation] = Field(description="At most 2 items")
    watch: List[Recommendation] = Field(description="At most 2 items")


class CompetitorReport(BaseModel):
    competitor_name: str
    executive_summary: str = Field(
        description="Clearest difference, where each side is stronger, what customers "
        f"value most, and the biggest strategic implication for a PM. Max 3 sentences."
    )
    sources: List[SourceSummary] = Field(description="The 3 to 5 most useful sources only")
    positioning: PositioningComparison
    feature_comparison: List[FeatureRow] = Field(
        description="3 to 5 meaningful dimensions only, not an exhaustive feature list"
    )
    customer_perception: CustomerPerception
    pricing: PricingComparison
    strategic_read: StrategicRead
    recommendations: Recommendations
    open_questions: List[str] = Field(
        description=f"At most 4 items: missing evidence and questions for customer "
        f"research, sales/support, or product analytics. {PHRASE} each."
    )
