from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--expected-tag', default='')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest.get('format') != 'youtube-ai-release-v2':
        raise SystemExit('unsupported manifest format')
    tag = str(manifest.get('release_tag', ''))
    if args.expected_tag and tag != args.expected_tag:
        raise SystemExit(f'manifest release tag mismatch: {tag} != {args.expected_tag}')
    required = [
        'app/db/migrations.py', 'app/config.py', 'Dockerfile', 'docker-compose.production.yml',
        'frontend/Dockerfile', 'frontend/package.json', 'app/auth/security.py', 'app/auth/authorization.py',
        'app/api/privacy.py', 'app/oauth/crypto.py', 'app/services/audit.py', 'app/privacy/service.py',
        'frontend/lib/api.ts', 'frontend/next.config.ts', 'deploy/SECURITY_PRIVACY.md',
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
    ]
    artifacts = manifest.get('artifacts', {})
    for name in required:
        expected = artifacts.get(name)
        if not expected:
            raise SystemExit(f'missing artifact hash: {name}')
        actual = sha256(ROOT / name)
        if actual != expected:
            raise SystemExit(f'artifact hash mismatch: {name}')
    if manifest.get('rollback_policy', {}).get('database_schema_rollback') is not False:
        raise SystemExit('database schema rollback policy must be false')
    refs = manifest.get('image_immutability', {})
    if manifest.get('api_image_ref') and not refs.get('api_digest_pinned'):
        raise SystemExit('api image ref must be digest pinned when present')
    if manifest.get('web_image_ref') and not refs.get('web_digest_pinned'):
        raise SystemExit('web image ref must be digest pinned when present')
    print('manifest_verified=true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
