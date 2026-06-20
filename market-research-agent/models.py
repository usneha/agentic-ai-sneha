from typing import List

from pydantic import BaseModel, Field


class CompetitorList(BaseModel):
    competitors: List[str] = Field(
        description="Exactly 3 specific competitor products or services."
    )


class CompetitorReport(BaseModel):
    competitor_name: str
    pricing_model: str = Field(
        description="How they make money, specific prices if found."
    )
    core_features: List[str] = Field(
        description="List of 3-5 main features."
    )
    market_positioning: str = Field(
        description="1-2 sentences on target customer and differentiation."
    )
    recent_news: str = Field(
        description="Any recent launches or news found."
    )
