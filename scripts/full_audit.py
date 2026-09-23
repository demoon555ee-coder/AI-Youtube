from __future__ import annotations
import ast, json, pathlib, re, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def internal_import_audit() -> list[tuple[str, str]]:
    missing=[]
    app=ROOT/'app'
    for f in app.rglob('*.py'):
        if '__pycache__' in f.parts: continue
        tree=ast.parse(f.read_text())
        for n in ast.walk(tree):
            targets=[]
            if isinstance(n, ast.ImportFrom) and n.level==0 and n.module and n.module.startswith('app.'):
                targets=[n.module]
            elif isinstance(n, ast.Import):
                targets=[a.name for a in n.names if a.name.startswith('app.')]
            for target in targets:
                base=app.joinpath(*target.split('.')[1:])
                if not (base.with_suffix('.py').exists() or (base/'__init__.py').exists()):
                    missing.append((str(f.relative_to(ROOT)), target))
    return missing


def route_audit() -> list[tuple[str, str]]:
    seen={}; duplicates=[]
    for f in (ROOT/'app/api').glob('*.py'):
        tree=ast.parse(f.read_text()); prefix=''
        for n in tree.body:
            if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='router' for t in n.targets):
                if isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id=='APIRouter':
                    for kw in n.value.keywords:
                        if kw.arg=='prefix' and isinstance(kw.value, ast.Constant): prefix=kw.value.value
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for d in n.decorator_list:
                    if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name) and d.func.value.id=='router' and d.args and isinstance(d.args[0],ast.Constant):
                        key=(d.func.attr.upper(), prefix+d.args[0].value)
                        if key in seen: duplicates.append((key, seen[key], str(f.relative_to(ROOT))))
                        else: seen[key]=str(f.relative_to(ROOT))
    return duplicates


def migration_audit():
    sys.path.insert(0, str(ROOT))
    from app.db.migrations import MIGRATIONS, _split_sql
    versions=[v for v,_ in MIGRATIONS]
    assert versions == sorted(versions, key=lambda x:int(x.split('_',1)[0]))
    counts={v:len(_split_sql(sql)) for v,sql in MIGRATIONS}
    return versions, counts


def secret_scan() -> list[str]:
    hits=[]
    patterns=[re.compile(r'AIza[0-9A-Za-z_-]{20,}'), re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----'), re.compile(r'(?i)sk-[A-Za-z0-9]{20,}')]
    tracked = None
    try:
        git_bin = shutil.which('git') or (r'C:\Program Files\Git\cmd\git.exe' if pathlib.Path(r'C:\Program Files\Git\cmd\git.exe').exists() else None)
        if git_bin:
            result = subprocess.run([git_bin, 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                tracked = {ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()}
    except OSError:
        tracked = None
    if tracked is None:
        files = (f for f in ROOT.rglob('*') if f.name != '.env' and not f.name.startswith('.env.') or f.name.endswith('.example'))
    else:
        files = tracked
    for f in files:
        if not f.is_file() or any(part in {'node_modules','.git','.pytest_cache','__pycache__','secrets'} for part in f.parts): continue
        if f.suffix.lower() in {'.pyc','.png','.mp4','.jpg','.jpeg','.wav','.mp3','.tar','.gz'}: continue
        try: text=f.read_text(errors='ignore')
        except Exception: continue
        for p in patterns:
            if p.search(text): hits.append(str(f.relative_to(ROOT)))
    return sorted(set(hits))


def _current_app_version() -> str:
    cfg = (ROOT / 'app/config.py').read_text()
    match = re.search(r'app_version: str = \"([^\"]+)\"', cfg)
    if not match:
        raise RuntimeError('app_version is not configured')
    return match.group(1)


def _current_release_defaults_match() -> bool:
    version = _current_app_version()
    checks = [
        (ROOT / 'docker-compose.yml').read_text(),
        (ROOT / 'docker-compose.staging.yml').read_text(),
        (ROOT / 'docker-compose.production.yml').read_text(),
        (ROOT / '.env.production.example').read_text(),
    ]
    return all(version in text and '3.8.0' not in text for text in checks[:2]) and version in checks[2] and version in checks[3] and 'prom/prometheus:v3.8.0' in checks[2]


def deployment_audit() -> dict:
    compose = (ROOT / 'docker-compose.production.yml').read_text()
    docker = (ROOT / 'Dockerfile').read_text()
    frontend = (ROOT / 'frontend/Dockerfile').read_text()
    return {
        'production_migration_gate': 'service_completed_successfully' in compose,
        'production_auto_migrate_disabled': 'AUTO_MIGRATE: \"false\"' in compose,
        'backend_non_root': 'USER app' in docker,
        'backend_healthcheck': 'HEALTHCHECK' in docker,
        'frontend_healthcheck': 'HEALTHCHECK' in frontend,
        'ci_present': (ROOT / '.github/workflows/ci.yml').exists(),
        'deploy_present': (ROOT / '.github/workflows/deploy.yml').exists(),
        'rollback_present': (ROOT / 'scripts/rollback.sh').exists(),
        'backup_present': (ROOT / 'scripts/backup_database.sh').exists(),
        'metrics_private_token': 'METRICS_PUBLIC=false' in (ROOT / '.env.production.example').read_text(),
        'compose_release_defaults_current': _current_release_defaults_match(),
        'staging_compose_present': (ROOT / 'docker-compose.staging.yml').exists(),
        'staging_migration_gate': 'service_completed_successfully' in (ROOT / 'docker-compose.staging.yml').read_text(),
        'frontend_api_build_arg': 'ARG NEXT_PUBLIC_API_BASE' in (ROOT / 'frontend/Dockerfile').read_text() and 'NEXT_PUBLIC_API_BASE' in (ROOT / 'docker-compose.staging.yml').read_text(),
        'staging_e2e_harness': all((ROOT / rel).exists() for rel in ['e2e/package.json', 'e2e/playwright.config.ts', 'e2e/tests/app.spec.ts']),
        'staging_e2e_ci_gate': 'staging_e2e:' in (ROOT / '.github/workflows/ci.yml').read_text() and 'needs: [backend, frontend, integration, staging_e2e' in (ROOT / '.github/workflows/ci.yml').read_text(),
        'v28_blue_green_compose': all((ROOT / rel).exists() for rel in ['docker-compose.bluegreen.yml', 'scripts/deploy_blue_green.sh', 'scripts/rollback_blue_green.sh']),
        'v28_release_manifest': all((ROOT / rel).exists() for rel in ['scripts/create_release_manifest.py', 'scripts/verify_release_manifest.py']),
        'v28_recovery_drill': all((ROOT / rel).exists() for rel in ['scripts/verify_backup.sh', 'scripts/restore_drill.sh']),
        'v28_rollback_workflow': (ROOT / '.github/workflows/rollback.yml').exists() and 'rollback_blue_green.sh' in (ROOT / '.github/workflows/rollback.yml').read_text(),
        'v28_release_history_migration': '016_v28_release_history' in (ROOT / 'app/db/migrations.py').read_text(),
    }


def production_ai_audit() -> dict:
    cfg = (ROOT / 'app/config.py').read_text()
    deployment = (ROOT / 'app/deployment.py').read_text()
    media_service = (ROOT / 'app/media/service.py').read_text()
    orchestration = (ROOT / 'app/services/orchestrator.py').read_text()
    env = (ROOT / '.env.production.example').read_text()
    return {
        'current_version_config': bool(re.search(r'app_version: str = "[0-9]+\.[0-9]+\.[0-9]+"', cfg)),
        'image_provider_config': 'image_provider:' in cfg and 'image_model:' in cfg,
        'video_provider_config': 'video_provider:' in cfg and 'video_timeout_seconds:' in cfg,
        'tts_provider_config': 'tts_provider:' in cfg and 'tts_model:' in cfg,
        'asset_factory_split': 'get_image_provider' in media_service and 'get_video_provider' in media_service,
        'orchestrator_supports_video': 'production_video' in orchestration,
        'orchestrator_supports_tts': 'tts_route' in orchestration,
        'media_job_model': (ROOT / 'app/models/media_job.py').exists(),
        'production_mock_ai_block': 'mock_llm_provider' in deployment and 'mock_video_provider' in deployment,
        'production_env_real_ai': (
            'LLM_PROVIDER=openai_compatible' in env
            and ('IMAGE_PROVIDER=openai_image' in env or 'IMAGE_PROVIDER=stability_image' in env)
            and ('VIDEO_PROVIDER=http_video' in env or 'VIDEO_PROVIDER=runway' in env)
            and ('TTS_PROVIDER=openai_tts' in env or 'TTS_PROVIDER=elevenlabs' in env)
        ),
    }



def resilience_audit() -> dict:
    router = (ROOT / 'app/routing/service.py').read_text()
    resilience = (ROOT / 'app/resilience/provider.py').read_text()
    http = (ROOT / 'app/resilience/http.py').read_text()
    media = (ROOT / 'app/media/recovery.py').read_text()
    worker = (ROOT / 'app/workflows/worker.py').read_text()
    dead_letter = (ROOT / 'app/models/dead_letter.py').read_text()
    media_model = (ROOT / 'app/models/media_job.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    return {
        'resilience_package_present': (ROOT / 'app/resilience/__init__.py').exists(),
        'circuit_breaker_states': all(x in resilience for x in ['CLOSED', 'OPEN', 'HALF_OPEN']),
        'circuit_retry_probe': 'provider_circuit_cooldown_seconds' in resilience and 'provider_half_open_seconds' in resilience,
        'retry_after_support': 'Retry-After' in http and 'should_retry_response' in http,
        'provider_routing_circuit_gate': 'ProviderReliabilityService' in router and 'provider_circuit_open' in router,
        'media_recovery': 'recover_existing_job' in media and 'DEAD_LETTER' in media,
        'worker_media_loop': '_media_recovery_loop' in worker and 'MediaRecoveryService' in worker,
        'workflow_dead_letter': (ROOT / 'app/models/dead_letter.py').exists() and 'WorkflowDeadLetter' in dead_letter,
        'media_job_idempotency': 'idempotency_key' in media_model and 'portfolio_id' in media_model,
        'resilience_migration': '019_v31_provider_resilience' in migration and '020_v32_quality_postpublish' in migration and '021_v33_content_evolution' in migration and '022_v34_creative_intelligence' in migration,
    }


def billing_audit() -> dict:
    api = (ROOT / 'app/api/billing.py').read_text()
    service = (ROOT / 'app/billing/service.py').read_text()
    provider = (ROOT / 'app/billing/providers.py').read_text()
    model = (ROOT / 'app/models/billing.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    return {
        'billing_api_present': '/api/v1/billing' in api,
        'dev_activation_blocked_in_production': '@router.post("/dev/activate")' in api and 'settings.app_env == "production"' in api,
        'idempotent_metering': 'BillingMeterEvent' in service and 'on_conflict_do_nothing' in service,
        'provider_abstraction': 'class BillingProvider' in provider,
        'billing_models_present': all(name in model for name in ['BillingPlan', 'BillingSubscription', 'BillingUsageCounter', 'BillingWebhookEvent']),
        'billing_migration_present': '013_v24_billing' in migration and '014_v25_real_billing_provider' in migration and '015_v25_webhook_reliability' in migration and 'billing_checkout_sessions' in migration,
        'production_billing_validation': 'mock_billing_provider' in (ROOT / 'app/deployment.py').read_text() and 'missing_billing_webhook_secret' in (ROOT / 'app/deployment.py').read_text() and 'missing_stripe_secret_key' in (ROOT / 'app/deployment.py').read_text(),
        'stripe_provider_present': 'class StripeBillingProvider' in provider and 'Stripe-Signature' in provider and '/v1/checkout/sessions' in provider,
        'webhook_async_queue': 'process_pending_webhooks' in service and 'status.in_({"RECEIVED", "RETRY"})' in service,
        'webhook_retry_fields': 'attempts' in model and 'next_attempt_at' in model,
        'checkout_reconciliation': 'BillingCheckoutSession' in model and 'checkout.session.completed' in service,
        'stripe_sandbox_script': (ROOT / 'scripts/stripe_sandbox_check.py').exists(),
    }



def integration_audit() -> dict:
    ci = (ROOT / '.github/workflows/ci.yml').read_text()
    dev = (ROOT / 'requirements-dev.txt').read_text()
    integration = (ROOT / 'requirements-integration.txt').read_text()
    return {
        'testcontainers_dependency': 'testcontainers[postgres]' in integration,
        'pytest_asyncio_dependency': 'pytest-asyncio' in dev,
        'integration_marker': 'integration:' in (ROOT / 'pytest.ini').read_text(),
        'postgres_matrix': "postgres-version: ['15', '16']" in ci,
        'python_matrix': "python-version: ['3.12', '3.13']" in ci,
        'integration_job_present': '  integration:' in ci and './scripts/run_integration_tests.sh' in ci,
        'image_publish_depends_on_integration': 'needs: [backend, frontend, integration, staging_e2e' in ci,
        'youtube_read_only_script': (ROOT / 'scripts/youtube_api_sandbox_check.py').exists() and 'videos' in (ROOT / 'scripts/youtube_api_sandbox_check.py').read_text(),
        'youtube_oauth_live_script': (ROOT / 'scripts/youtube_oauth_live_check.py').exists() and 'YOUTUBE_OAUTH_CALLBACK_URL' in (ROOT / 'scripts/youtube_oauth_live_check.py').read_text(),
        'provider_contract_tests': (ROOT / 'tests/test_provider_contracts.py').exists(),
        'postgres_integration_tests': (ROOT / 'tests/integration/test_postgres_real.py').exists(),
        'staging_playwright_harness': all((ROOT / rel).exists() for rel in ['e2e/package.json', 'e2e/playwright.config.ts', 'e2e/tests/app.spec.ts']),
    }

def security_audit() -> dict:
    main = (ROOT / 'app/main.py').read_text()
    authz = (ROOT / 'app/auth/authorization.py').read_text()
    auth_api = (ROOT / 'app/api/auth.py').read_text()
    oauth = (ROOT / 'app/services/youtube_service.py').read_text()
    frontend_api = (ROOT / 'frontend/lib/api.ts').read_text()
    return {
        'global_auth_guard': 'dependencies=[Depends(enforce_request_authorization)]' in main,
        'production_docs_disabled': 'docs_url=None if settings.app_env == "production"' in main,
        'tenant_owner_guard': 'Cross-organization owner_id is not allowed' in authz,
        'api_key_mutation_guard': 'Read-only API keys are denied all mutations' in authz,
        'cross_tenant_youtube_protection': 'already connected to another organization' in oauth,
        'auth_api_present': '/auth' in auth_api or 'prefix="/api/v1/auth"' in auth_api,
        'frontend_cookie_auth': 'credentials: "include"' in frontend_api,
        'authorization_settings_import': 'from app.config import settings' in authz,
        'cross_origin_sse_credentials': 'withCredentials:true' in (ROOT / 'frontend/app/projects/[id]/page.tsx').read_text(),
        'csrf_synchronizer_protection': 'await enforce_csrf(request, db, principal)' in authz and 'X-CSRF-Token' in (ROOT / 'app/config.py').read_text(),
        'csrf_token_encrypted': 'csrf_token_enc' in (ROOT / 'app/models/auth.py').read_text() and 'encrypt(raw)' in (ROOT / 'app/auth/security.py').read_text(),
        'origin_defense': 'Origin not allowed' in (ROOT / 'app/auth/security.py').read_text(),
        'secure_cookie_production': 'secure=settings.app_env == "production"' in auth_api and '__Host-' in (ROOT / '.env.production.example').read_text(),
        'csp_present': 'Content-Security-Policy' in main and 'Content-Security-Policy' in (ROOT / 'frontend/next.config.ts').read_text(),
        'privacy_router_present': (ROOT / 'app/api/privacy.py').exists() and 'prefix="/api/v1/privacy"' in (ROOT / 'app/api/privacy.py').read_text() and '@router.get("/export")' in (ROOT / 'app/api/privacy.py').read_text(),
        'privacy_worker_present': 'process_deletion_request' in (ROOT / 'app/workflows/worker.py').read_text(),
        'retention_policy_present': all(key in (ROOT / 'app/config.py').read_text() for key in ['audit_retention_days', 'usage_retention_days', 'privacy_request_retention_days']),
        'encryption_rotation_script': (ROOT / 'scripts/rotate_encryption_keys.py').exists(),
        'security_migration_v29': '017_v29_security_privacy' in (ROOT / 'app/db/migrations.py').read_text(),
    }


def quality_audit() -> dict:
    service = (ROOT / 'app/quality/service.py').read_text()
    agent = (ROOT / 'app/agents/qa.py').read_text()
    api = (ROOT / 'app/api/quality.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    return {
        'quality_service_present': (ROOT / 'app/quality/service.py').exists(),
        'ffprobe_media_probe': 'ffprobe' in service and 'has_audio' in service and 'has_video' in service,
        'quality_persistent_report': 'VideoQualityReport' in service and 'video_quality_reports' in migration,
        'qa_quality_gate': 'quality.get("status") == "FAIL"' in agent,
        'quality_api_present': 'prefix="/api/v1/quality"' in api,
        'quality_migration_present': '020_v32_quality_postpublish' in migration,
    }


def evolution_audit() -> dict:
    model = (ROOT / 'app/models/evolution.py').read_text()
    service = (ROOT / 'app/evolution/service.py').read_text()
    api = (ROOT / 'app/api/evolution.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    main = (ROOT / 'app/main.py').read_text()
    return {
        'evolution_model_present': 'ContentVersion' in model and 'ContentArtifact' in model,
        'immutable_lineage': all(x in model for x in ['parent_project_id', 'content_root_id', 'revision_number']),
        'revision_service': 'create_revision' in service and 'pg_advisory_xact_lock' in service and 'do_not_modify_source' in service,
        'artifact_hashing': '_sha256_file' in service and 'hashlib.sha256' in service,
        'evolution_api_present': 'prefix="/api/v1/evolution"' in api and '/projects/{project_id}/revisions' in api,
        'postpublish_reedit_route': '/alerts/{alert_id}/create-revision' in (ROOT / 'app/api/postpublish.py').read_text(),
        'migration_present': '021_v33_content_evolution' in migration and 'content_artifacts' in migration,
        'router_registered': 'evolution_router' in main and 'app.include_router(evolution_router)' in main,
    }


def creative_audit() -> dict:
    service = (ROOT / 'app/creative_intelligence/service.py').read_text()
    api = (ROOT / 'app/api/creative.py').read_text()
    model = (ROOT / 'app/models/creative.py').read_text()
    vision = (ROOT / 'app/vision/openai.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    main = (ROOT / 'app/main.py').read_text()
    return {
        'creative_service_present': 'class CreativeIntelligenceService' in service,
        'frame_extraction': '_extract_frame' in service and 'ffmpeg' in service,
        'visual_metrics': '_visual_metrics' in service and 'duplicate_transition_count' in service,
        'audio_metrics': '_audio_metrics' in service and 'volumedetect' in service,
        'scene_reports': '_scene_reports' in service and 'narration_visual_alignment' in service,
        'targeted_reedit': 'class TargetedReEditService' in service and 'render_patch' in service,
        'vision_provider': 'input_image' in vision and '/responses' in vision,
        'model_present': 'CreativeAnalysis' in model and 'creative_analyses' in model,
        'api_present': 'prefix="/api/v1/creative"' in api and '/projects/{project_id}/analyze' in api and '/projects/{project_id}/reedit' in api,
        'reedit_permission_guard': 'permission_dependency("content:write")' in api,
        'migration_present': '022_v34_creative_intelligence' in migration and 'creative_analyses' in migration,
        'router_registered': 'creative_router' in main and 'app.include_router(creative_router)' in main,
    }


def creative_director_audit() -> dict:
    service = (ROOT / 'app/creative_director/service.py').read_text()
    model = (ROOT / 'app/models/creative_director.py').read_text()
    api = (ROOT / 'app/api/creative.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    docs = (ROOT / 'deploy/CREATIVE_DIRECTOR.md').read_text()
    return {
        'service_present': 'class CreativeDirectorService' in service and 'VALID_ACTIONS' in service,
        'bounded_changes': 'max_changes' in service and 'min(int(max_changes), 12)' in service,
        'action_normalization': 'manual_review' in service and 'replace_visual' in service and 'tighten' in service,
        'execution_summary': '_execution_summary' in service and 'supported_actions' in service,
        'model_present': 'CreativeDirectorDecision' in model and 'creative_director_decisions' in model,
        'api_present': '/projects/{project_id}/director-plan' in api and '/projects/{project_id}/director-plans' in api,
        'permission_guard': 'permission_dependency("content:write")' in api,
        'server_side_provider_selection': 'project.data or {}' in api and 'routing_plan' in api and 'llm_config' not in api[api.find('class DirectorPlanRequest'):api.find('def _serialize_director')],
        'migration_present': '023_v35_creative_director' in migration and 'creative_director_decisions' in migration,
        'docs_present': 'Only `replace_visual` and `tighten` are executable' in docs,
    }

def postpublish_audit() -> dict:
    service = (ROOT / 'app/postpublish/service.py').read_text()
    api = (ROOT / 'app/api/postpublish.py').read_text()
    worker = (ROOT / 'app/workflows/worker.py').read_text()
    model = (ROOT / 'app/models/quality.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    return {
        'postpublish_service_present': (ROOT / 'app/postpublish/service.py').exists(),
        'postpublish_monitor_model': 'PostPublishMonitor' in model and 'PerformanceAlert' in model,
        'anomaly_detection': '_detect' in service and 'retention' in service and 'impression_ctr' in service,
        'alert_deduplication': 'dedupe_key' in service and 'with_for_update' in service,
        'auto_correct_guard': 'do_not_modify_published_video_without_explicit experiment_policy' in service,
        'worker_loop': '_postpublish_loop' in worker and 'PostPublishMonitorService' in worker,
        'postpublish_api_present': 'prefix="/api/v1/post-publish"' in api,
        'postpublish_migration_present': '020_v32_quality_postpublish' in migration,
    }


def control_plane_audit() -> dict:
    runtime = (ROOT / 'app/runtime/service.py').read_text()
    runtime_api = (ROOT / 'app/api/runtime.py').read_text()
    planner = (ROOT / 'app/planner/service.py').read_text()
    governance = (ROOT / 'app/governance/service.py').read_text()
    execution = (ROOT / 'app/execution/controller.py').read_text()
    learning = (ROOT / 'app/learning/service.py').read_text()
    learning_api = (ROOT / 'app/api/learning.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    return {
        'migration_031_present': '031_v421_agent_control_plane_correction' in migration,
        'runtime_governed_on_create': 'evaluate_action' in runtime and 'TASK_ADMITTED' in runtime,
        'runtime_rechecks_before_lease': 'Re-admit against the current policy immediately before execution.' in runtime and 'policy_changed' in runtime,
        'runtime_lease_required_for_terminal': 'lease_token: str' in runtime and 'await self._get_live_lease(task_id, lease_token)' in runtime,
        'runtime_same_tenant_lineage': '_assert_same_channel_task' in runtime and 'channel_id == channel_id' in runtime,
        'runtime_cycle_detection': '_would_create_cycle' in runtime and 'task_dependency_cycle' in runtime,
        'runtime_api_no_duplicate_budget_binding': '**payload.model_dump(),\n            budget_usd=' not in runtime_api,
        'runtime_api_worker_mutations_restricted': 'require_roles({"owner", "admin"})' in runtime_api and 'require_roles({"owner", "admin", "editor"})' not in runtime_api,
        'planner_uses_learning_strategy': 'active_strategy' in planner,
        'planner_rechecks_governance_on_materialization': 'self.runtime.create_task' in planner and 'requested_mode="auto"' in planner,
        'planner_cycle_validation': '_validate_acyclic' in planner,
        'planner_replan_limit': 'planner_max_retries' in planner,
        'governance_safe_unknown_action_default': 'CRITICAL' in governance and 'automation_mode": "block"' in governance,
        'governance_current_approval_version': 'approval_policy_version' in execution and 'approval_is_current' in execution,
        'learning_authoritative_outcome_source': 'record_task_outcome' in learning and 'source_type="agent_task"' in learning,
        'learning_forbids_governance_learning': 'FORBIDDEN_STRATEGY_KEYS' in learning and 'max_cost_usd' in learning and 'permissions' in learning,
        'learning_requires_human_activation': 'PENDING_APPROVAL' in learning and 'activated_by_user_id' in learning,
        'learning_api_does_not_accept_fabricated_observations': '@router.post("/channels/{channel_id}/observations")' not in learning_api,
    }


def multimodal_audit() -> dict:
    service = (ROOT / 'app/multimodal_graph/service.py').read_text()
    model = (ROOT / 'app/models/multimodal.py').read_text()
    api = (ROOT / 'app/api/multimodal.py').read_text()
    main = (ROOT / 'app/main.py').read_text()
    vision = (ROOT / 'app/vision/openai.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    orchestrator = (ROOT / 'app/services/orchestrator.py').read_text()
    return {
        'service_present': 'class MultimodalProductionGraphService' in service and 'build_preflight' in service and 'analyze_rendered' in service,
        'graph_model_present': 'ProductionMultimodalGraph' in model and 'production_multimodal_graphs' in model,
        'graph_links_modalities': all(token in service for token in ['script', 'storyboard', 'timeline', 'subtitle', 'audio', 'visual']),
        'preflight_audio_check': 'audio_overrun_risk' in service and '_estimate_speech_seconds' in service,
        'postrender_media_probe': 'probe_media' in service and '_extract_frames' in service,
        'real_audio_probe': 'volumedetect' in service and 'audio_analysis' in service,
        'multi_image_vision': 'analyze_multimodal' in vision and 'input_image' in vision and '/responses' in vision,
        'api_present': 'prefix="/api/v1/multimodal"' in api and '/projects/{project_id}/preflight' in api and '/projects/{project_id}/analyze' in api,
        'write_permission_guard': 'permission_dependency("content:write")' in api,
        'router_registered': 'multimodal_router' in main and 'app.include_router(multimodal_router)' in main,
        'orchestrator_preflight': 'MultimodalProductionGraphService' in orchestrator and 'multimodal_preflight_hard_fail' in orchestrator,
        'migration_present': '024_v36_multimodal_production_graph' in migration and 'production_multimodal_graphs' in migration,
        'docs_env': 'MULTIMODAL_GRAPH_ENABLED' in (ROOT / '.env.example').read_text(),
    }


def autonomous_optimization_audit() -> dict:
    model = (ROOT / 'app/models/autonomous_optimization.py').read_text()
    service = (ROOT / 'app/autonomous_optimization.py').read_text()
    api = (ROOT / 'app/api/autonomous_optimization.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    main = (ROOT / 'app/main.py').read_text()
    ui = (ROOT / 'frontend/app/optimization/page.tsx').read_text()
    config = (ROOT / 'app/config.py').read_text()
    env = (ROOT / '.env.example').read_text()
    return {
        'model_present': 'AutonomousOptimizationDecision' in model and 'autonomous_optimization_decisions' in model,
        'service_present': 'class AutonomousOptimizationService' in service and '_deterministic_plan' in service,
        'bounded_scopes': 'TARGET_SCOPES' in service and 'scene_reedit' in service and 'packaging_experiment' in service and 'blueprint_replan' in service,
        'published_immutability_guard': 'published_source_immutable' in service and 'requires_quality_gate' in service,
        'llm_fallback': 'generate_json' in service and '_deterministic_plan' in service and 'except Exception' in service,
        'api_present': 'prefix="/api/v1/optimization"' in api and '/projects/{project_id}/decide' in api and '/channels/{channel_id}/decisions' in api,
        'write_permission_guard': 'permission_dependency("content:write")' in api,
        'router_registered': 'autonomous_optimization_router' in main and 'app.include_router(autonomous_optimization_router)' in main,
        'postpublish_integration': 'AutonomousOptimizationService' in (ROOT / 'app/postpublish/service.py').read_text(),
        'migration_present': '025_v37_autonomous_optimization' in migration and 'autonomous_optimization_decisions' in migration,
        'ui_present': 'Autonomous Optimization' in ui,
        'config_present': 'optimization_ai_enabled' in config and 'optimization_default_max_actions' in config,
        'env_docs': 'OPTIMIZATION_AI_ENABLED' in env,
        'optimization_config': 'optimization_ai_enabled' in config and all(token in (ROOT / '.env.production.example').read_text() for token in ['OPTIMIZATION_AI_ENABLED', 'OPTIMIZATION_MIN_CONFIDENCE', 'OPTIMIZATION_DEFAULT_MAX_ACTIONS', 'OPTIMIZATION_AUTO_EXECUTE']),
    }


def autonomous_execution_audit() -> dict:
    model = (ROOT / 'app/models/execution.py').read_text()
    service = (ROOT / 'app/execution/controller.py').read_text()
    api = (ROOT / 'app/api/execution.py').read_text()
    migration = (ROOT / 'app/db/migrations.py').read_text()
    main = (ROOT / 'app/main.py').read_text()
    env = (ROOT / '.env.production.example').read_text()
    config = (ROOT / 'app/config.py').read_text()
    workflow = (ROOT / 'app/workflows/engine.py').read_text()
    ui = (ROOT / 'frontend/app/execution/page.tsx').read_text()
    return {
        'model_present': 'AutonomousExecutionRun' in model and 'autonomous_execution_runs' in model,
        'bounded_modes': all(token in service for token in ['auto', 'approve', 'defer', 'block']),
        'bounded_scopes': all(token in service for token in ['scene_reedit', 'packaging_experiment', 'blueprint_replan', 'full_rebuild']),
        'permission_guard': 'content:write' in api and 'permission_dependency("content:write")' in api,
        'quality_guard': 'execution_require_quality_gate' in service and 'VideoQualityReport' in service,
        'daily_revision_guard': 'execution_max_revisions_per_day' in service and 'revision_number' in service,
        'budget_reservation': 'PortfolioManager' in service and '_reserve' in service,
        'idempotency': 'idempotency_key' in model and 'idempotency_key' in service,
        'targeted_scene_execution': 'targeted_scene_reedit' in service and 'ContentEvolutionService' in service,
        'workflow_reconciliation': 'reconcile_workflow' in service and 'reconcile_workflow' in workflow,
        'api_present': 'prefix="/api/v1/execution"' in api and '/decisions/{decision_id}/dispatch' in api and '/runs/{run_id}/execute' in api,
        'router_registered': 'execution_router' in main and 'app.include_router(execution_router)' in main,
        'migration_present': '028_v40_multi_agent_runtime' in migration and 'agent_tasks' in migration and 'agent_leases' in migration,
        'config_present': all(k in config for k in ['execution_controller_enabled', 'execution_require_quality_gate', 'execution_default_reservation_ttl_minutes', 'execution_max_revisions_per_day']),
        'env_docs': 'EXECUTION_CONTROLLER_ENABLED' in env and 'EXECUTION_REQUIRE_QUALITY_GATE' in env,
        'ui_present': 'Execution Runs' in ui or 'Autonomous Execution' in ui,
        'production_ai_not_mocked': 'mock_llm_provider' not in service and 'mock_video_provider' not in service,
    }



if __name__=='__main__':
    versions, migration_counts = migration_audit()
    payload={
        'python_compile': subprocess.run([sys.executable,'-m','compileall','-q','app'], cwd=ROOT, check=False).returncode==0,
        'internal_import_missing': internal_import_audit(),
        'duplicate_routes': route_audit(),
        'migration_versions': versions,
        'migration_statement_counts': migration_counts,
        'secret_scan_hits': secret_scan(),
        'security': security_audit(),
        'deployment': deployment_audit(),
        'billing': billing_audit(),
        'integration': integration_audit(),
        'production_ai': production_ai_audit(),
        'resilience': resilience_audit(),
        'quality': quality_audit(),
        'postpublish': postpublish_audit(),
        'evolution': evolution_audit(),
        'creative': creative_audit(),
        'creative_director': creative_director_audit(),
        'multimodal': multimodal_audit(),
        'autonomous_optimization': autonomous_optimization_audit(),
        'autonomous_execution': autonomous_execution_audit(),
        'control_plane': control_plane_audit(),
    }
    print(json.dumps(payload, indent=2, default=str))
    failures = []
    if not payload['python_compile']: failures.append('compileall')
    if payload['internal_import_missing']: failures.append('internal imports')
    if payload['duplicate_routes']: failures.append('duplicate routes')
    if payload['secret_scan_hits']: failures.append('secrets')
    if not all(payload['security'].values()): failures.append('security controls')
    if not all(payload['deployment'].values()): failures.append('deployment controls')
    if not all(payload['billing'].values()): failures.append('billing controls')
    if not all(payload['integration'].values()): failures.append('integration controls')
    if not all(payload['production_ai'].values()): failures.append('production AI controls')
    if not all(payload['resilience'].values()): failures.append('resilience controls')
    if not all(payload['quality'].values()): failures.append('quality controls')
    if not all(payload['postpublish'].values()): failures.append('postpublish controls')
    if not all(payload['evolution'].values()): failures.append('evolution controls')
    if not all(payload['creative'].values()): failures.append('creative intelligence controls')
    if not all(payload['creative_director'].values()): failures.append('creative director controls')
    if not all(payload['multimodal'].values()): failures.append('multimodal production graph controls')
    if not all(payload['autonomous_optimization'].values()): failures.append('autonomous optimization controls')
    if not all(payload['autonomous_execution'].values()): failures.append('autonomous execution controls')
    if not all(payload['control_plane'].values()): failures.append('agent control plane controls')
    raise SystemExit(1 if failures else 0)
