from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def git_rev() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return 'unknown'


def latest_schema() -> str:
    import sys
    sys.path.insert(0, str(ROOT))
    from app.db.migrations import MIGRATIONS
    return MIGRATIONS[-1][0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('tag')
    parser.add_argument('-o', '--output', type=Path, default=Path('RELEASE_MANIFEST.json'))
    parser.add_argument('--api-image-ref', default='')
    parser.add_argument('--web-image-ref', default='')
    parser.add_argument('--previous-tag', default='')
    args = parser.parse_args()
    if not args.tag or not args.tag[0].isdigit():
        raise SystemExit('invalid release tag')
    files = [
        'app/db/migrations.py',
        'app/config.py',
        'Dockerfile',
        'docker-compose.production.yml',
        'frontend/Dockerfile',
        'frontend/package.json',
        'app/auth/security.py',
        'app/auth/authorization.py',
        'app/api/privacy.py',
        'app/oauth/crypto.py',
        'app/services/audit.py',
        'app/privacy/service.py',
        'frontend/lib/api.ts',
        'frontend/next.config.ts',
        'deploy/SECURITY_PRIVACY.md',
        'scripts/rotate_encryption_keys.py',
        'app/media/service.py',
        'app/media/openai_image.py',
        'app/media/http_image.py',
        'app/media/http_video.py',
        'app/media/mock_video.py',
        'app/tts/openai.py',
        'app/tts/factory.py',
        'app/agents/production.py',
        'app/services/orchestrator.py',
        'app/models/media_job.py',
        'app/media/url_guard.py',
        'deploy/PRODUCTION_AI.md',
        'deploy/PROVIDER_RESILIENCE.md',
        'app/resilience/http.py',
        'app/resilience/provider.py',
        'app/media/recovery.py',
        'app/models/provider_reliability.py',
        'app/models/dead_letter.py',
        'app/workflows/engine.py',
        'app/workflows/worker.py',
        'app/models/quality.py',
        'app/quality/service.py',
        'app/api/quality.py',
        'app/postpublish/service.py',
        'app/api/postpublish.py',
        '.env.example',
        'app/quality/service.py',
        'app/models/quality.py',
        'app/api/quality.py',
        'app/postpublish/service.py',
        'app/api/postpublish.py',
        'frontend/app/quality/page.tsx',
        'frontend/app/post-publish/page.tsx',
        'app/evolution/service.py',
        'app/evolution/__init__.py',
        'app/models/evolution.py',
        'app/api/evolution.py',
        'deploy/CONTENT_EVOLUTION.md',
        'frontend/app/evolution/page.tsx',
        'tests/test_v33_content_evolution.py',
        'tests/test_v32_quality.py',
        'tests/test_v32_postpublish.py',
        '.env.production.example',
        'app/vision/base.py',
        'app/vision/factory.py',
        'app/vision/mock.py',
        'app/vision/openai.py',
        'app/creative_intelligence/service.py',
        'app/models/creative.py',
        'app/api/creative.py',
        'deploy/CREATIVE_INTELLIGENCE.md',
        'frontend/app/creative/page.tsx',
        'tests/test_v34_creative.py',
        'tests/test_v34_creative_static.py',
        'app/creative_director/service.py',
        'app/creative_director/__init__.py',
        'app/models/creative_director.py',
        'deploy/CREATIVE_DIRECTOR.md',
        'tests/test_v35_creative_director.py',
        'tests/test_v35_static.py',
        'app/multimodal_graph/__init__.py',
        'app/autonomous_optimization.py',
        'app/models/autonomous_optimization.py',
        'app/api/autonomous_optimization.py',
        'frontend/app/optimization/page.tsx',
        'tests/test_v37_optimization.py',
        'deploy/AUTONOMOUS_OPTIMIZATION.md',

        'app/multimodal_graph/service.py',
        'app/models/multimodal.py',
        'app/api/multimodal.py',
        'app/vision/base.py',
        'app/vision/mock.py',
        'app/vision/openai.py',
        'deploy/MULTIMODAL_PRODUCTION_GRAPH.md',
        'frontend/app/multimodal/page.tsx',
        'frontend/components/Shell.tsx',
        'tests/test_v36_multimodal.py',
        'tests/test_v36_multimodal_static.py',
        'app/execution/__init__.py',
        'app/execution/controller.py',
        'app/models/execution.py',
        'app/api/execution.py',
        'app/workflows/engine.py',
        'deploy/AUTONOMOUS_EXECUTION.md',
        'frontend/app/execution/page.tsx',
        'tests/test_v38_execution.py',
        'scripts/full_audit.py',
        'AUDIT_REPORT.md',
        'app/governance/service.py',
        'app/models/governance.py',
        'app/api/governance.py',
        'deploy/AGENT_GOVERNANCE.md',
        'tests/test_v39_governance.py',
        'app/runtime/__init__.py',
        'app/runtime/service.py',
        'app/models/agent_runtime.py',
        'app/api/runtime.py',
        'frontend/app/agents/page.tsx',
        'deploy/AGENT_RUNTIME.md',
        'tests/test_v40_agent_runtime.py',
        'app/planner/__init__.py',
        'app/planner/service.py',
        'app/models/planner.py',
        'app/api/planner.py',
        'frontend/app/planner/page.tsx',
        'deploy/AGENT_PLANNER.md',
        'tests/test_v41_planner.py',
        'app/learning/__init__.py',
        'app/learning/service.py',
        'app/models/learning.py',
        'app/api/learning.py',
        'frontend/app/learning/page.tsx',
        'deploy/AGENT_LEARNING.md',
        'tests/test_v42_learning.py',
        'tests/test_v421_control_plane_logic.py',
        'tests/test_v39_governance.py',
        'app/execution/controller.py',
        'tests/test_v38_execution.py',
    ]
    manifest = {
        'format': 'youtube-ai-release-v2',
        'release_tag': args.tag,
        'previous_release_tag': args.previous_tag or None,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': git_rev(),
        'schema_version': latest_schema(),
        'api_image_ref': args.api_image_ref or None,
        'web_image_ref': args.web_image_ref or None,
        'image_immutability': {
            'api_digest_pinned': bool(args.api_image_ref and '@sha256:' in args.api_image_ref),
            'web_digest_pinned': bool(args.web_image_ref and '@sha256:' in args.web_image_ref),
        },
        'artifacts': {name: sha256(ROOT / name) for name in files},
        'rollback_policy': {
            'application_only': True,
            'database_schema_rollback': False,
            'compatibility_policy': 'expand_contract',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
