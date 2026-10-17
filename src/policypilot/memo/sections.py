"""The six sections of Contoso Bank's credit memo template, and what the agent must look for
in a 10-K for each. Keys match the legacy `memo_sections.section_type` values exactly."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: str
    goal: str
    queries: tuple[str, ...]


SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        key="business_overview",
        title="1. Business Overview",
        goal=(
            "Describe what the borrower does: principal products and services, business "
            "segments, geographic footprint, and main sources of revenue."
        ),
        queries=(
            "company business overview products and services",
            "reportable segments description",
            "revenue by geographic region",
        ),
    ),
    SectionSpec(
        key="industry_competition",
        title="2. Industry & Competitive Position",
        goal=(
            "Summarise the competitive environment: key competitors or competitive factors, "
            "market position, and industry dynamics the borrower describes."
        ),
        queries=(
            "competition competitive factors market",
            "industry conditions and trends",
            "competitive position strengths",
        ),
    ),
    SectionSpec(
        key="financial_performance",
        title="3. Financial Performance",
        goal=(
            "Summarise recent financial performance: net sales or revenue, profitability "
            "(gross margin, operating income, net income) and the reasons the borrower gives "
            "for year-over-year changes. Quote figures exactly as stated."
        ),
        queries=(
            "net sales revenue increased decreased compared to prior year",
            "gross margin operating income net income",
            "results of operations fiscal year",
        ),
    ),
    SectionSpec(
        key="liquidity_debt",
        title="4. Liquidity & Debt Structure",
        goal=(
            "Describe liquidity and capital structure: cash and marketable securities, "
            "outstanding debt (notes, commercial paper, credit facilities), maturities, and "
            "material cash requirements or capital return programs."
        ),
        queries=(
            "liquidity and capital resources cash marketable securities",
            "outstanding debt notes commercial paper credit facility",
            "debt maturities contractual obligations cash requirements",
        ),
    ),
    SectionSpec(
        key="key_risks",
        title="5. Key Risk Factors",
        goal=(
            "Identify the most credit-relevant risk factors the borrower discloses (for "
            "example supply chain concentration, competition, regulation, macroeconomic "
            "exposure), focusing on risks that could affect repayment capacity."
        ),
        queries=(
            "risk factors could materially adversely affect business",
            "dependence on suppliers concentration risk",
            "macroeconomic conditions adverse effect results",
        ),
    ),
    SectionSpec(
        key="legal_regulatory",
        title="6. Legal & Regulatory Matters",
        goal=(
            "Summarise material legal proceedings, regulatory investigations, and laws or "
            "regulations the borrower says could materially affect it."
        ),
        queries=(
            "legal proceedings litigation",
            "regulatory investigations government",
            "laws and regulations compliance could affect",
        ),
    ),
)

SECTION_BY_KEY = {s.key: s for s in SECTIONS}
