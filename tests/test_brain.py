from app.brain.analyzer import ChannelBrainAnalyzer, VideoMetricRow


def test_channel_brain_builds_baseline():
    rows = [
        VideoMetricRow(video_id="a", views=1000, avg_view_percentage=45),
        VideoMetricRow(video_id="b", views=2000, avg_view_percentage=55),
        VideoMetricRow(video_id="c", views=3000, avg_view_percentage=65),
    ]
    result = ChannelBrainAnalyzer().analyze_channel(rows)
    assert "summary" in result
    assert result["learned_patterns"]


def test_video_optimizer_detects_low_retention():
    baseline = ChannelBrainAnalyzer().analyze_channel([
        VideoMetricRow(video_id="a", views=1000, avg_view_percentage=60),
        VideoMetricRow(video_id="b", views=1100, avg_view_percentage=62),
        VideoMetricRow(video_id="c", views=1200, avg_view_percentage=64),
    ])
    result = ChannelBrainAnalyzer().optimize_video(
        VideoMetricRow(video_id="x", views=900, avg_view_percentage=40),
        baseline,
    )
    assert result["actions"]


def test_video_optimizer_uses_subscriber_baseline():
    baseline = ChannelBrainAnalyzer().analyze_channel([
        VideoMetricRow(video_id="a", views=1000, subscribers_gained=10, avg_view_percentage=50),
        VideoMetricRow(video_id="b", views=1100, subscribers_gained=12, avg_view_percentage=52),
        VideoMetricRow(video_id="c", views=1200, subscribers_gained=14, avg_view_percentage=54),
    ])
    result = ChannelBrainAnalyzer().optimize_video(
        VideoMetricRow(video_id="x", views=1000, subscribers_gained=20, avg_view_percentage=52),
        baseline,
    )
    assert result["diagnosis"]["subscriber_signal"] == "positive"
