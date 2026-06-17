from __future__ import annotations

from textwrap import dedent

from backend.app.models import CompanyRecord, MarkdownExport


def _bullets(items: list[str]) -> str:
    if not items:
        return "- To be developed."
    return "\n".join(f"- {item}" for item in items)


def build_substack_markdown(company: CompanyRecord) -> MarkdownExport:
    profile = company.profile
    thesis = company.thesis
    valuation = company.valuation
    selected = getattr(valuation, valuation.selected_case)
    catalysts = "\n".join(
        f"- **{item.timing}:** {item.title} ({item.impact}, {item.status})"
        for item in thesis.catalysts
    ) or "- To be developed."

    markdown = dedent(
        f"""
        # {profile.name} ({profile.ticker}): {thesis.one_liner or "Investment Thesis Draft"}

        > Disclosure: This is personal research, not investment advice. Market data may come from free/public sources or sanitized fixtures; validate figures before publishing.

        ## Setup
        - **Recommendation:** {company.recommendation.rating} ({company.recommendation.confidence} confidence)
        - **Source status:** {company.recommendation.source_status}
        - **Horizon:** {thesis.horizon}
        - **Sector:** {profile.sector} / {profile.industry}
        - **Market cap:** {profile.market_cap:.1f}B {profile.currency}
        - **Current quoted price:** {company.market.price:.2f}

        ## Recommendation Rationale
        {company.recommendation.rationale}

        ## Recent News Context
        {chr(10).join(f"- **{item.published_at} / {item.source}:** {item.title} - {item.summary}" for item in company.news) or "- Add current news review here."}

        ## Variant View
        {thesis.variant_view or "Write the differentiated view here."}

        ## Evidence
        {_bullets(thesis.evidence)}

        ## Valuation
        - **Selected case:** {valuation.selected_case.title()}
        - **Implied price:** {selected.implied_price:.2f}
        - **Implied return:** {selected.implied_return_pct:.1f}%
        - **Revenue CAGR:** {selected.revenue_cagr_pct:.1f}%
        - **Terminal margin:** {selected.terminal_margin_pct:.1f}%
        - **Exit multiple:** {selected.exit_multiple:.1f}x

        {valuation.notes or "Add valuation bridge and sensitivity commentary here."}

        ## Catalysts
        {catalysts}

        ## Risks
        {_bullets(thesis.risks)}

        ## Watch Items
        {_bullets(thesis.watch_items)}
        """
    ).strip()

    return MarkdownExport(
        ticker=profile.ticker,
        filename=f"{profile.ticker.lower()}-thesis-brief.md",
        markdown=markdown,
    )
