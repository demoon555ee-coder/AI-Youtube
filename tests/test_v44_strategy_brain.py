import uuid
from types import SimpleNamespace

from app.strategy.service import PortfolioStrategyBrain


def test_portfolio_structure_assigns_roles():
    rows = [{"channel": {"id": str(uuid.uuid4()), "name": "A"}, "digital_twin": {"recent_28d": {"views": 100, "watch_time_minutes": 20}}}, {"channel": {"id": str(uuid.uuid4()), "name": "B"}, "digital_twin": {"recent_28d": {"views": 50, "watch_time_minutes": 10}}}]
    result = PortfolioStrategyBrain._portfolio_structure(rows)
    assert [x["role"] for x in result] == ["core_growth", "experimental_growth"]


def test_video_slate_is_capped():
    channels = [{"channel": {"id": "1", "name": "A"}, "growth_hypotheses": [{"topic": f"t{i}", "strength": 1 / (i + 1), "evidence": {}} for i in range(40)]}]
    assert len(PortfolioStrategyBrain._video_slate(channels, 10)) == 10
