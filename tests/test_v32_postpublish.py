from types import SimpleNamespace

from app.postpublish.service import PostPublishMonitorService


def test_baseline_uses_median():
    rows = [
        SimpleNamespace(views=10, average_view_percentage=50, impression_ctr=4),
        SimpleNamespace(views=20, average_view_percentage=60, impression_ctr=5),
        SimpleNamespace(views=1000, average_view_percentage=70, impression_ctr=6),
    ]
    baseline = PostPublishMonitorService._baseline(rows)
    assert baseline["views"] == 20
    assert baseline["average_view_percentage"] == 60
    assert baseline["impression_ctr"] == 5


def test_detector_flags_material_retention_drop():
    latest = SimpleNamespace(views=25, average_view_percentage=40, impression_ctr=3)
    baseline = {"views": 20, "average_view_percentage": 60, "impression_ctr": 5}
    anomalies = PostPublishMonitorService._detect(latest, baseline, 20)
    assert anomalies["retention"]["delta_pct"] == -33.33
    assert anomalies["retention"]["severity"] == "medium"
    assert "views" not in anomalies
    assert "ctr" in anomalies


def test_detector_does_not_alert_for_small_changes():
    latest = SimpleNamespace(views=19, average_view_percentage=57, impression_ctr=4.8)
    baseline = {"views": 20, "average_view_percentage": 60, "impression_ctr": 5}
    anomalies = PostPublishMonitorService._detect(latest, baseline, 20)
    assert anomalies == {}


def test_remediation_is_guarded():
    remediation = PostPublishMonitorService._remediation("ctr", True)
    assert remediation["action"] == "review_title_and_thumbnail"
    assert remediation["auto_correct_requested"] is True
    assert "do_not_modify_published_video" in remediation["guardrail"]
