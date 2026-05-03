from __future__ import annotations

from omnibot.schemas.events import AgentResult, ArbiterDecision


class PresenceLayer:
    """Turns internal coordination into a clean, legible response."""

    def compose(self, request: str, decision: ArbiterDecision, results: list[AgentResult]) -> str:
        tools = sorted({tool for result in results for tool in result.tool_calls})
        sources = sorted({source for result in results for source in result.sources})
        score = decision.coherence_score
        return (
            f"{decision.final_answer}\n\n"
            "What I did:\n"
            f"- Ran {len(results)} agents in parallel: {', '.join(r.agent_name for r in results)}.\n"
            f"- Used tools: {', '.join(tools) if tools else 'none'}.\n"
            f"- Sources: {', '.join(sources[:8]) if sources else 'none'}.\n"
            f"- Arbiter confidence: {decision.confidence:.2f}.\n\n"
            "Coherence score:\n"
            f"- Overall: {score.overall:.2f}\n"
            f"- Evidence coverage: {score.evidence_coverage:.2f}\n"
            f"- Agent agreement: {score.agent_agreement:.2f}\n"
            f"- Tool provenance: {score.tool_provenance:.2f}\n"
            f"- Confidence spread: {score.confidence_spread:.2f}\n"
            f"- Unresolved risk: {score.unresolved_risk:.2f}\n\n"
            "Why this answer:\n"
            f"{decision.rationale}"
        )
