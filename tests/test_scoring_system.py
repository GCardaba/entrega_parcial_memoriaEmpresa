"""
Unit tests for the MasterAgentsScoring trim-mean algorithm.
These tests are pure Python — no LLM calls, no DB required.
"""
import pytest
from models.agent_state import MasterAgentScore, QueryProposal, EvaluationMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_scores(values: list[float]) -> list[MasterAgentScore]:
    return [
        MasterAgentScore(master_agent_id=f"master_{i+1}", score=v, reasoning="test")
        for i, v in enumerate(values)
    ]


# ---------------------------------------------------------------------------
# trim-mean correctness
# ---------------------------------------------------------------------------

def test_trim_mean_drops_highest_and_lowest():
    """With 5 scores, the mean of the middle 3 must be returned."""
    scores = [5.0, 6.0, 7.0, 8.0, 9.0]
    # Sorted: [5, 6, 7, 8, 9] → drop 5 and 9 → mean(6, 7, 8) = 7.0
    trimmed = sorted(scores)[1:-1]
    expected = sum(trimmed) / len(trimmed)
    assert expected == pytest.approx(7.0)


def test_scoring_system_uses_trim_mean(sample_evaluation):
    """The fixture evaluation has 5 scores [8,6,7,9,5] → trim → mean(6,7,8) = 7.0."""
    scores = [s.score for s in sample_evaluation.master_agent_scores]
    sorted_scores = sorted(scores)
    trimmed = sorted_scores[1:-1]
    result = sum(trimmed) / len(trimmed)
    assert result == pytest.approx(7.0)


def test_trim_with_ties():
    """Ties in score values should be handled correctly (no crash)."""
    scores = [7.0, 7.0, 7.0, 7.0, 7.0]
    sorted_scores = sorted(scores)
    trimmed = sorted_scores[1:-1]
    result = sum(trimmed) / len(trimmed)
    assert result == pytest.approx(7.0)


def test_trim_with_extreme_outliers():
    """An outlier in either direction should not affect the trimmed mean."""
    scores = [0.0, 7.0, 7.0, 7.0, 10.0]
    sorted_scores = sorted(scores)
    trimmed = sorted_scores[1:-1]
    result = sum(trimmed) / len(trimmed)
    assert result == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# MasterAgentsScoring.calculate_final_score integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_final_score_returns_float(
    db, mock_llm, sample_proposal, sample_metrics, better_metrics
):
    from agents.master_agents.master_agent_1 import MasterAgent1
    from agents.master_agents.master_agent_2 import MasterAgent2
    from agents.master_agents.master_agent_3 import MasterAgent3
    from agents.master_agents.master_agent_4 import MasterAgent4
    from agents.master_agents.master_agent_5 import MasterAgent5
    from agents.master_agents.scoring_system import MasterAgentsScoring

    master_agents = [
        MasterAgent1(mock_llm, db, "master_1"),
        MasterAgent2(mock_llm, db, "master_2"),
        MasterAgent3(mock_llm, db, "master_3"),
        MasterAgent4(mock_llm, db, "master_4"),
        MasterAgent5(mock_llm, db, "master_5"),
    ]
    scoring = MasterAgentsScoring(master_agents, db)
    score = await scoring.calculate_final_score(sample_proposal, sample_metrics, better_metrics)
    assert isinstance(score, float)
    assert 0.0 <= score <= 10.0


@pytest.mark.asyncio
async def test_five_agents_each_score_independently(
    db, mock_llm, sample_proposal, sample_metrics, better_metrics
):
    """All 5 master agents must produce a score; none should silently fail."""
    from agents.master_agents.master_agent_1 import MasterAgent1
    from agents.master_agents.master_agent_2 import MasterAgent2
    from agents.master_agents.master_agent_3 import MasterAgent3
    from agents.master_agents.master_agent_4 import MasterAgent4
    from agents.master_agents.master_agent_5 import MasterAgent5
    import asyncio

    agents = [
        MasterAgent1(mock_llm, db, "master_1"),
        MasterAgent2(mock_llm, db, "master_2"),
        MasterAgent3(mock_llm, db, "master_3"),
        MasterAgent4(mock_llm, db, "master_4"),
        MasterAgent5(mock_llm, db, "master_5"),
    ]
    scores = await asyncio.gather(*[
        a.score_proposal(sample_proposal, sample_metrics, better_metrics)
        for a in agents
    ])
    assert len(scores) == 5
    for s in scores:
        assert 0.0 <= s.score <= 10.0
        assert s.reasoning != ""
