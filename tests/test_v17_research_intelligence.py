from app.research.opportunity import OpportunityDetector
from app.research.youtube_data import YouTubeDataResearchProvider
from app.research.graph_service import ResearchGraphService
from app.models.research_graph import ResearchNode, ResearchEdge, ResearchOpportunity


def sample_results():
    return [
        {"id": "a", "title": "AI agents for developers", "channel_id": "c1", "channel_title": "A", "views": 1_000_000, "published_at": "2026-09-10T00:00:00Z"},
        {"id": "b", "title": "How AI coding agents work", "channel_id": "c2", "channel_title": "B", "views": 500_000, "published_at": "2026-09-12T00:00:00Z"},
        {"id": "c", "title": "The future of AI programming", "channel_id": "c3", "channel_title": "C", "views": 120_000, "published_at": "2026-09-01T00:00:00Z"},
    ]


def test_opportunity_detector_returns_bounded_signal():
    result = OpportunityDetector().detect(
        channel={"name": "Test", "niche": "AI programming", "language": "en"},
        query="AI coding agents",
        results=sample_results(),
        node_ids=["1", "2", "3"],
    )
    assert len(result) == 1
    signal = result[0]
    for value in [signal.score, signal.demand_signal, signal.competition_signal, signal.freshness_signal, signal.gap_signal, signal.channel_fit]:
        assert 0 <= value <= 1
    assert "sample_size" in signal.rationale


def test_youtube_provider_contract():
    provider = YouTubeDataResearchProvider(api_key="key", order="bad")
    assert provider.name == "youtube_data_api"
    assert provider.order == "viewCount"


def test_graph_service_exports():
    assert hasattr(ResearchGraphService, "scan")
    assert ResearchNode.__tablename__ == "research_nodes"
    assert ResearchEdge.__tablename__ == "research_edges"
    assert ResearchOpportunity.__tablename__ == "research_opportunities"
