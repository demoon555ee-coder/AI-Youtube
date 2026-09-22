from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_v11",
        """
        ALTER TABLE optimization_reports
            ADD COLUMN IF NOT EXISTS video_project_id UUID NULL;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attrelid = c.conrelid
                    AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'optimization_reports'::regclass
                    AND c.contype = 'f'
                    AND a.attname = 'video_project_id'
            ) THEN
                ALTER TABLE optimization_reports
                    ADD CONSTRAINT fk_optimization_reports_video_project
                    FOREIGN KEY (video_project_id) REFERENCES video_projects(id) ON DELETE SET NULL;
            END IF;
        END $$;
        CREATE INDEX IF NOT EXISTS ix_optimization_reports_video_project_id ON optimization_reports(video_project_id);

        ALTER TABLE analytics_snapshots
            ADD COLUMN IF NOT EXISTS impressions INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE analytics_snapshots
            ADD COLUMN IF NOT EXISTS impression_ctr DOUBLE PRECISION NOT NULL DEFAULT 0;

        CREATE TABLE IF NOT EXISTS content_experiments (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            video_project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            experiment_type VARCHAR(50) NOT NULL DEFAULT 'observational',
            dimension VARCHAR(50) NOT NULL DEFAULT 'title',
            hypothesis TEXT NOT NULL DEFAULT '',
            variants JSONB NOT NULL DEFAULT '{}'::jsonb,
            decision_rule JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            started_at TIMESTAMP NULL,
            ended_at TIMESTAMP NULL,
            result JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_content_experiments_channel_status ON content_experiments(channel_id, status);

        CREATE TABLE IF NOT EXISTS experiment_observations (
            id UUID PRIMARY KEY,
            experiment_id UUID NOT NULL REFERENCES content_experiments(id) ON DELETE CASCADE,
            variant_key VARCHAR(100) NOT NULL,
            observed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            views INTEGER NOT NULL DEFAULT 0,
            impressions INTEGER NOT NULL DEFAULT 0,
            ctr DOUBLE PRECISION NOT NULL DEFAULT 0,
            average_view_percentage DOUBLE PRECISION NOT NULL DEFAULT 0,
            watch_time_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
            subscribers_gained INTEGER NOT NULL DEFAULT 0,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_experiment_observation_point UNIQUE (experiment_id, variant_key, observed_at)
        );
        CREATE INDEX IF NOT EXISTS ix_experiment_observations_experiment ON experiment_observations(experiment_id, observed_at);

        CREATE TABLE IF NOT EXISTS research_reports (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            video_project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            query TEXT NOT NULL,
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            competitor_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
            audience_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
            content_gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT NOT NULL DEFAULT '',
            provider VARCHAR(100) NOT NULL DEFAULT 'mock',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_research_reports_channel_created ON research_reports(channel_id, created_at);
        """,
    ),
    (
        "002_v12_autopilot",
        """
ALTER TABLE channels
            ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'UTC';

        ALTER TABLE publications
            ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP NULL;

        CREATE TABLE IF NOT EXISTS content_plans (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            goal VARCHAR(30) NOT NULL DEFAULT 'balanced',
            cadence_per_week INTEGER NOT NULL DEFAULT 3,
            publish_time VARCHAR(5) NOT NULL DEFAULT '18:00',
            weekdays JSONB NOT NULL DEFAULT '[]'::jsonb,
            production_lead_hours INTEGER NOT NULL DEFAULT 24,
            auto_publish BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_content_plans_channel_status ON content_plans(channel_id, status);

        CREATE TABLE IF NOT EXISTS content_plan_items (
            id UUID PRIMARY KEY,
            plan_id UUID NOT NULL REFERENCES content_plans(id) ON DELETE CASCADE,
            idea_id UUID NULL REFERENCES content_ideas(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            position INTEGER NOT NULL,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            hook TEXT NOT NULL DEFAULT '',
            angle TEXT NOT NULL DEFAULT '',
            format VARCHAR(50) NOT NULL DEFAULT 'long_form',
            scheduled_for TIMESTAMP NOT NULL,
            production_start_at TIMESTAMP NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_content_plan_item_position UNIQUE(plan_id, position)
        );
        CREATE INDEX IF NOT EXISTS ix_content_plan_items_due ON content_plan_items(status, production_start_at);
        CREATE INDEX IF NOT EXISTS ix_content_plan_items_plan_schedule ON content_plan_items(plan_id, scheduled_for);
        """,
    ),
    (
        "003_v13_content_intelligence",
        """
        CREATE TABLE IF NOT EXISTS content_blueprints (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            idea_id UUID NULL REFERENCES content_ideas(id) ON DELETE SET NULL,
            plan_item_id UUID NULL REFERENCES content_plan_items(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            format VARCHAR(50) NOT NULL DEFAULT 'explainer',
            hook_pattern VARCHAR(50) NOT NULL DEFAULT 'question',
            target_duration_minutes INTEGER NOT NULL DEFAULT 10,
            visual_change_seconds DOUBLE PRECISION NOT NULL DEFAULT 4.5,
            narrative_structure JSONB NOT NULL DEFAULT '{}'::jsonb,
            packaging JSONB NOT NULL DEFAULT '{}'::jsonb,
            experiment_spec JSONB NOT NULL DEFAULT '{}'::jsonb,
            reasoning JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_content_blueprints_channel_created ON content_blueprints(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_content_blueprints_channel_status ON content_blueprints(channel_id, status);
        CREATE INDEX IF NOT EXISTS ix_content_blueprints_idea_id ON content_blueprints(idea_id);
        CREATE INDEX IF NOT EXISTS ix_content_blueprints_plan_item_id ON content_blueprints(plan_item_id);
        CREATE INDEX IF NOT EXISTS ix_content_blueprints_project_id ON content_blueprints(project_id);
        """,
    ),
    (
        "004_v14_portfolio",
        """
        CREATE TABLE IF NOT EXISTS portfolios (
            id UUID PRIMARY KEY,
            owner_id VARCHAR(120) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL DEFAULT 'My YouTube Portfolio',
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            monthly_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            daily_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_portfolios_owner_id ON portfolios(owner_id);

        CREATE TABLE IF NOT EXISTS portfolio_channels (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            budget_weight DOUBLE PRECISION NOT NULL DEFAULT 1,
            monthly_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_portfolio_channel UNIQUE(portfolio_id, channel_id)
        );
        CREATE INDEX IF NOT EXISTS ix_portfolio_channels_portfolio ON portfolio_channels(portfolio_id);
        CREATE INDEX IF NOT EXISTS ix_portfolio_channels_channel ON portfolio_channels(channel_id);

        CREATE TABLE IF NOT EXISTS provider_budgets (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            provider VARCHAR(100) NOT NULL,
            service VARCHAR(100) NOT NULL DEFAULT 'general',
            monthly_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            daily_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            hard_limit BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_provider_budget UNIQUE(portfolio_id, provider, service)
        );

        CREATE TABLE IF NOT EXISTS cost_events (
            id UUID PRIMARY KEY,
            owner_id VARCHAR(120) NOT NULL DEFAULT 'local-user',
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            agent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
            provider VARCHAR(100) NOT NULL,
            service VARCHAR(100) NOT NULL DEFAULT 'general',
            unit VARCHAR(50) NOT NULL DEFAULT 'request',
            quantity DOUBLE PRECISION NOT NULL DEFAULT 1,
            unit_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_cost_events_portfolio_created ON cost_events(portfolio_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_cost_events_channel_created ON cost_events(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_cost_events_project_created ON cost_events(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_cost_events_provider_created ON cost_events(provider, created_at);
        """,
    ),
    (
        "005_v15_cost_aware_routing",
        """
        CREATE TABLE IF NOT EXISTS provider_profiles (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            provider VARCHAR(100) NOT NULL,
            service VARCHAR(100) NOT NULL DEFAULT 'llm',
            kind VARCHAR(100) NOT NULL DEFAULT 'mock',
            quality_tier VARCHAR(30) NOT NULL DEFAULT 'standard',
            priority INTEGER NOT NULL DEFAULT 100,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            unit VARCHAR(50) NOT NULL DEFAULT 'request',
            unit_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_provider_profile UNIQUE(portfolio_id, provider, service)
        );
        CREATE INDEX IF NOT EXISTS ix_provider_profiles_portfolio_service ON provider_profiles(portfolio_id, service, enabled);

        CREATE TABLE IF NOT EXISTS routing_decisions (
            id UUID PRIMARY KEY,
            owner_id VARCHAR(120) NOT NULL DEFAULT 'local-user',
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            agent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
            step_name VARCHAR(100) NOT NULL,
            service VARCHAR(100) NOT NULL,
            requested_tier VARCHAR(30) NOT NULL DEFAULT 'standard',
            chosen_provider VARCHAR(100) NOT NULL,
            chosen_tier VARCHAR(30) NOT NULL DEFAULT 'standard',
            fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            reason VARCHAR(500) NOT NULL DEFAULT '',
            candidates_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_routing_decisions_project_created ON routing_decisions(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_routing_decisions_portfolio_created ON routing_decisions(portfolio_id, created_at);
        """,
    ),
    (
        "006_v16_portfolio_manager",
        """
        CREATE TABLE IF NOT EXISTS portfolio_policies (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL UNIQUE REFERENCES portfolios(id) ON DELETE CASCADE,
            planning_horizon_days INTEGER NOT NULL DEFAULT 30,
            reserve_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.10,
            target_utilization_pct DOUBLE PRECISION NOT NULL DEFAULT 80,
            max_channel_concentration_pct DOUBLE PRECISION NOT NULL DEFAULT 50,
            min_channel_allocation_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_daily_buffer_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS portfolio_allocations (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            allocation_date DATE NOT NULL,
            target_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            reserved_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            projected_spend_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            budget_weight DOUBLE PRECISION NOT NULL DEFAULT 1,
            fairness_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            rank INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_portfolio_allocation_day UNIQUE(portfolio_id, channel_id, allocation_date)
        );
        CREATE INDEX IF NOT EXISTS ix_portfolio_allocations_portfolio_date ON portfolio_allocations(portfolio_id, allocation_date);

        CREATE TABLE IF NOT EXISTS portfolio_decisions (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            decision_type VARCHAR(50) NOT NULL,
            action VARCHAR(80) NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_portfolio_decisions_portfolio_created ON portfolio_decisions(portfolio_id, created_at);

        CREATE TABLE IF NOT EXISTS budget_reservations (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            purpose VARCHAR(100) NOT NULL DEFAULT 'production',
            idempotency_key VARCHAR(255) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            expires_at TIMESTAMP NOT NULL,
            released_at TIMESTAMP NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_budget_reservation_key UNIQUE(portfolio_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_budget_reservations_portfolio_status ON budget_reservations(portfolio_id, status);
        CREATE INDEX IF NOT EXISTS ix_budget_reservations_expires ON budget_reservations(status, expires_at);
        """,
    ),
    (
        "007_v17_research_intelligence",
        """
        ALTER TABLE content_ideas ADD COLUMN IF NOT EXISTS research_opportunity_id UUID NULL;
        CREATE INDEX IF NOT EXISTS ix_content_ideas_research_opportunity_id ON content_ideas(research_opportunity_id);
        CREATE TABLE IF NOT EXISTS research_nodes (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            node_type VARCHAR(40) NOT NULL DEFAULT 'topic',
            external_id VARCHAR(255) NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            url TEXT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_research_node_identity UNIQUE(channel_id, node_type, external_id)
        );
        CREATE INDEX IF NOT EXISTS ix_research_nodes_channel_type ON research_nodes(channel_id, node_type);
        CREATE INDEX IF NOT EXISTS ix_research_nodes_channel_created ON research_nodes(channel_id, created_at);

        CREATE TABLE IF NOT EXISTS research_edges (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            source_node_id UUID NOT NULL REFERENCES research_nodes(id) ON DELETE CASCADE,
            target_node_id UUID NOT NULL REFERENCES research_nodes(id) ON DELETE CASCADE,
            relation VARCHAR(60) NOT NULL DEFAULT 'related_to',
            weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_research_edge_identity UNIQUE(channel_id, source_node_id, target_node_id, relation)
        );
        CREATE INDEX IF NOT EXISTS ix_research_edges_channel_relation ON research_edges(channel_id, relation);

        CREATE TABLE IF NOT EXISTS research_opportunities (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            topic TEXT NOT NULL,
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            demand_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            competition_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            freshness_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            gap_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            channel_fit DOUBLE PRECISION NOT NULL DEFAULT 0,
            rationale JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_node_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_research_opportunities_channel_score ON research_opportunities(channel_id, score);
        CREATE INDEX IF NOT EXISTS ix_research_opportunities_channel_status ON research_opportunities(channel_id, status);
        """,
    ),

    (
        "008_v18_research_scheduler",
        """
        ALTER TABLE research_opportunities ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(64) NOT NULL DEFAULT '';

        ALTER TABLE research_opportunities ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

        ALTER TABLE research_opportunities ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1;

        CREATE INDEX IF NOT EXISTS ix_research_opportunities_fingerprint ON research_opportunities(channel_id, fingerprint);

        CREATE INDEX IF NOT EXISTS ix_research_opportunities_last_seen ON research_opportunities(channel_id, last_seen_at);

        UPDATE research_opportunities
        SET fingerprint = md5(lower(trim(query)) || '::' || lower(trim(topic)))
        WHERE fingerprint = '';

        CREATE TABLE IF NOT EXISTS research_schedules (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            name VARCHAR(160) NOT NULL,
            query TEXT NOT NULL,
            provider VARCHAR(80) NULL,
            cadence_hours DOUBLE PRECISION NOT NULL DEFAULT 24,
            next_run_at TIMESTAMP NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            max_results INTEGER NOT NULL DEFAULT 10,
            published_after_days INTEGER NULL,
            auto_generate_ideas BOOLEAN NOT NULL DEFAULT FALSE,
            idea_count INTEGER NOT NULL DEFAULT 5,
            goal VARCHAR(30) NOT NULL DEFAULT 'balanced',
            catch_up BOOLEAN NOT NULL DEFAULT FALSE,
            max_runs_per_day INTEGER NOT NULL DEFAULT 3,
            locked_until TIMESTAMP NULL,
            last_run_at TIMESTAMP NULL,
            last_status VARCHAR(30) NOT NULL DEFAULT 'NEVER_RUN',
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_research_schedule_channel_name UNIQUE(channel_id, name)
        );

        CREATE INDEX IF NOT EXISTS ix_research_schedules_due ON research_schedules(enabled, next_run_at, locked_until);

        CREATE INDEX IF NOT EXISTS ix_research_schedules_channel ON research_schedules(channel_id, enabled);

        CREATE TABLE IF NOT EXISTS research_runs (
            id UUID PRIMARY KEY,
            schedule_id UUID NOT NULL REFERENCES research_schedules(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            provider VARCHAR(80) NOT NULL DEFAULT 'mock',
            trigger_type VARCHAR(30) NOT NULL DEFAULT 'scheduled',
            status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL,
            result_count INTEGER NOT NULL DEFAULT 0,
            opportunity_count INTEGER NOT NULL DEFAULT 0,
            generated_idea_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_research_runs_schedule_started ON research_runs(schedule_id, started_at);

        CREATE INDEX IF NOT EXISTS ix_research_runs_channel_started ON research_runs(channel_id, started_at);

        CREATE INDEX IF NOT EXISTS ix_research_runs_status ON research_runs(status, started_at);
        """,
    ),

    (
        "009_v19_trend_diff",
        """
        CREATE TABLE IF NOT EXISTS research_snapshots (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            schedule_id UUID NULL REFERENCES research_schedules(id) ON DELETE SET NULL,
            run_id UUID NULL REFERENCES research_runs(id) ON DELETE SET NULL,
            query TEXT NOT NULL,
            provider VARCHAR(80) NOT NULL DEFAULT 'mock',
            captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            result_count INTEGER NOT NULL DEFAULT 0,
            avg_views DOUBLE PRECISION NOT NULL DEFAULT 0,
            max_views DOUBLE PRECISION NOT NULL DEFAULT 0,
            unique_channels INTEGER NOT NULL DEFAULT 0,
            topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_research_snapshots_channel_query_time ON research_snapshots(channel_id, query, captured_at);
        CREATE INDEX IF NOT EXISTS ix_research_snapshots_channel_run ON research_snapshots(channel_id, run_id);

        CREATE TABLE IF NOT EXISTS trend_events (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            snapshot_id UUID NOT NULL REFERENCES research_snapshots(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            topic_key VARCHAR(120) NOT NULL,
            topic_label TEXT NOT NULL,
            event_type VARCHAR(40) NOT NULL,
            current_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            previous_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            delta_signal DOUBLE PRECISION NOT NULL DEFAULT 0,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            rationale JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_trend_event_snapshot_topic_type UNIQUE(channel_id, snapshot_id, topic_key, event_type)
        );
        CREATE INDEX IF NOT EXISTS ix_trend_events_channel_created ON trend_events(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_trend_events_channel_type ON trend_events(channel_id, event_type);
        CREATE INDEX IF NOT EXISTS ix_trend_events_channel_topic ON trend_events(channel_id, topic_key);
        """,
    ),

    (
        "010_v20_opportunity_intelligence",
        """
        CREATE TABLE IF NOT EXISTS opportunity_analysis_runs (
            id UUID PRIMARY KEY,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            goal VARCHAR(30) NOT NULL DEFAULT 'balanced',
            status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
            opportunity_count INTEGER NOT NULL DEFAULT 0,
            actionable_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL,
            error_message TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_opportunity_analysis_runs_channel_created ON opportunity_analysis_runs(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_opportunity_analysis_runs_status ON opportunity_analysis_runs(status, created_at);

        CREATE TABLE IF NOT EXISTS opportunity_decisions (
            id UUID PRIMARY KEY,
            analysis_run_id UUID NOT NULL REFERENCES opportunity_analysis_runs(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            opportunity_id UUID NOT NULL REFERENCES research_opportunities(id) ON DELETE CASCADE,
            trend_event_id UUID NULL REFERENCES trend_events(id) ON DELETE SET NULL,
            priority_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            base_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            trend_boost DOUBLE PRECISION NOT NULL DEFAULT 0,
            urgency DOUBLE PRECISION NOT NULL DEFAULT 0,
            recommended_format VARCHAR(50) NOT NULL DEFAULT 'explainer',
            recommended_hook VARCHAR(50) NOT NULL DEFAULT 'question',
            recommended_duration_minutes INTEGER NOT NULL DEFAULT 10,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            action VARCHAR(40) NOT NULL DEFAULT 'EXPLORE',
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIONABLE',
            rationale JSONB NOT NULL DEFAULT '{}'::jsonb,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_opportunity_decision_run_opp UNIQUE(analysis_run_id, opportunity_id)
        );
        CREATE INDEX IF NOT EXISTS ix_opportunity_decisions_channel_created ON opportunity_decisions(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_opportunity_decisions_channel_score ON opportunity_decisions(channel_id, priority_score);
        CREATE INDEX IF NOT EXISTS ix_opportunity_decisions_run ON opportunity_decisions(analysis_run_id);

        """,
    ),

    (
        "011_v21_saas_security",
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            email VARCHAR(320) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name VARCHAR(255) NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_organizations_slug ON organizations(slug);

        CREATE TABLE IF NOT EXISTS memberships (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(30) NOT NULL DEFAULT 'viewer',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_membership_org_user UNIQUE(organization_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_memberships_org ON memberships(organization_id);
        CREATE INDEX IF NOT EXISTS ix_memberships_user ON memberships(user_id);

        CREATE TABLE IF NOT EXISTS auth_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NULL,
            revoked_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_auth_sessions_token ON auth_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_expires ON auth_sessions(user_id, expires_at);

        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            prefix VARCHAR(32) NOT NULL,
            key_hash VARCHAR(64) NOT NULL UNIQUE,
            scopes JSONB NOT NULL DEFAULT '["read"]'::jsonb,
            expires_at TIMESTAMP NULL,
            last_used_at TIMESTAMP NULL,
            revoked_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_api_keys_org_status ON api_keys(organization_id, revoked_at, expires_at);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE CASCADE,
            actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(100) NOT NULL,
            resource_id VARCHAR(255) NULL,
            ip_address VARCHAR(64) NULL,
            user_agent VARCHAR(500) NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_audit_logs_org_created ON audit_logs(organization_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_audit_logs_resource ON audit_logs(resource_type, resource_id);

        CREATE TABLE IF NOT EXISTS usage_events (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            service VARCHAR(100) NOT NULL,
            action VARCHAR(100) NOT NULL,
            units DOUBLE PRECISION NOT NULL DEFAULT 1,
            unit VARCHAR(50) NOT NULL DEFAULT 'request',
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_usage_events_org_created ON usage_events(organization_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_usage_events_org_service ON usage_events(organization_id, service, created_at);

        ALTER TABLE channels ADD COLUMN IF NOT EXISTS organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_channels_organization_id ON channels(organization_id);
        ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_portfolios_organization_id ON portfolios(organization_id);
        """,
    ),
    (
        "012_v22_observability",
        """
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            id UUID PRIMARY KEY,
            worker_id VARCHAR(255) NOT NULL UNIQUE,
            role VARCHAR(50) NOT NULL DEFAULT 'workflow',
            host VARCHAR(255) NOT NULL DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'STARTING',
            active_workflow_id UUID NULL,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_worker_heartbeats_last_seen ON worker_heartbeats(last_seen_at);
        CREATE INDEX IF NOT EXISTS ix_worker_heartbeats_active_workflow ON worker_heartbeats(active_workflow_id);
        """,
    ),
    (
        "013_v24_billing",
        """
        CREATE TABLE IF NOT EXISTS billing_plans (
            id UUID PRIMARY KEY,
            code VARCHAR(60) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            monthly_price_cents INTEGER NOT NULL DEFAULT 0,
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            entitlements JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_billing_plans_active ON billing_plans(active);

        CREATE TABLE IF NOT EXISTS billing_accounts (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL DEFAULT 'mock',
            customer_reference VARCHAR(255) NULL UNIQUE,
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_billing_account_org UNIQUE(organization_id)
        );

        CREATE TABLE IF NOT EXISTS billing_subscriptions (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            plan_id UUID NOT NULL REFERENCES billing_plans(id) ON DELETE RESTRICT,
            provider_subscription_reference VARCHAR(255) NULL UNIQUE,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            current_period_start TIMESTAMP NOT NULL,
            current_period_end TIMESTAMP NOT NULL,
            cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_org_status ON billing_subscriptions(organization_id, status);
        CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_period_end ON billing_subscriptions(current_period_end);

        CREATE TABLE IF NOT EXISTS billing_invoices (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            provider_invoice_reference VARCHAR(255) NULL UNIQUE,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            subtotal_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL DEFAULT 0,
            period_start TIMESTAMP NOT NULL,
            period_end TIMESTAMP NOT NULL,
            hosted_invoice_url TEXT NULL,
            paid_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_billing_invoices_org_period ON billing_invoices(organization_id, period_start, period_end);
        CREATE INDEX IF NOT EXISTS ix_billing_invoices_status ON billing_invoices(status);

        CREATE TABLE IF NOT EXISTS billing_usage_counters (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            period_start TIMESTAMP NOT NULL,
            period_end TIMESTAMP NOT NULL,
            metric VARCHAR(100) NOT NULL,
            units DOUBLE PRECISION NOT NULL DEFAULT 0,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_billing_usage_counter UNIQUE(organization_id, period_start, metric)
        );
        CREATE INDEX IF NOT EXISTS ix_billing_usage_counters_org_period ON billing_usage_counters(organization_id, period_start, period_end);

        CREATE TABLE IF NOT EXISTS billing_meter_events (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            idempotency_key VARCHAR(255) NOT NULL,
            service VARCHAR(100) NOT NULL,
            units DOUBLE PRECISION NOT NULL DEFAULT 0,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_billing_meter_event UNIQUE(organization_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_billing_meter_events_org_created ON billing_meter_events(organization_id, created_at);

        CREATE TABLE IF NOT EXISTS billing_webhook_events (
            id UUID PRIMARY KEY,
            provider VARCHAR(50) NOT NULL,
            external_event_reference VARCHAR(255) NOT NULL,
            event_type VARCHAR(120) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NULL,
            processed_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_billing_webhook_event UNIQUE(provider, external_event_reference)
        );
        CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_status ON billing_webhook_events(status, created_at);
        """,
    ),


    (
        "014_v25_real_billing_provider",
        """
        ALTER TABLE billing_plans
            ADD COLUMN IF NOT EXISTS provider_price_reference VARCHAR(255) NULL;
        CREATE INDEX IF NOT EXISTS ix_billing_plans_provider_price ON billing_plans(provider_price_reference);

        CREATE TABLE IF NOT EXISTS billing_checkout_sessions (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,
            external_checkout_reference VARCHAR(255) NOT NULL,
            plan_code VARCHAR(60) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
            url TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            completed_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_billing_checkout_reference UNIQUE(provider, external_checkout_reference)
        );
        CREATE INDEX IF NOT EXISTS ix_billing_checkout_org_created ON billing_checkout_sessions(organization_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_billing_checkout_status ON billing_checkout_sessions(status, created_at);
        """,
    ),


    (
        "015_v25_webhook_reliability",
        """
        ALTER TABLE billing_webhook_events
            ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE billing_webhook_events
            ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP NULL;
        CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_retry ON billing_webhook_events(status, next_attempt_at, created_at);
        """,
    ),

    (
        "016_v28_release_history",
        """
        CREATE TABLE IF NOT EXISTS release_deployments (
            id UUID PRIMARY KEY,
            release_id VARCHAR(255) NOT NULL,
            release_tag VARCHAR(100) NOT NULL,
            manifest_sha256 VARCHAR(64) NOT NULL,
            previous_release_tag VARCHAR(100) NULL,
            slot VARCHAR(20) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'STARTED',
            proxy_switched BOOLEAN NOT NULL DEFAULT FALSE,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_release_deployments_release_tag ON release_deployments(release_tag);
        CREATE INDEX IF NOT EXISTS ix_release_deployments_started_at ON release_deployments(started_at);
        """,
    ),

    (
        "017_v29_security_privacy",
        """
        ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS csrf_token_enc TEXT NOT NULL DEFAULT '';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS anonymized_at TIMESTAMP NULL;

        CREATE TABLE IF NOT EXISTS privacy_requests (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            request_type VARCHAR(40) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'REQUESTED',
            reason TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL
        );
        CREATE INDEX IF NOT EXISTS ix_privacy_requests_user_created ON privacy_requests(user_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_privacy_requests_org_created ON privacy_requests(organization_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_privacy_requests_status_created ON privacy_requests(status, created_at);

        CREATE TABLE IF NOT EXISTS login_rate_limits (
            key_hash VARCHAR(64) PRIMARY KEY,
            window_started_at TIMESTAMP NOT NULL,
            failure_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TIMESTAMP NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_login_rate_limits_blocked_until ON login_rate_limits(blocked_until);
        """,
    ),
    (
        "018_v30_real_ai_production",
        """
        CREATE TABLE IF NOT EXISTS media_generation_jobs (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE CASCADE,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            agent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
            scene_number INTEGER NOT NULL,
            provider VARCHAR(100) NOT NULL,
            external_job_id VARCHAR(255),
            status VARCHAR(30) NOT NULL DEFAULT 'QUEUED',
            status_url TEXT,
            output_url TEXT,
            request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_poll_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_media_jobs_project_created ON media_generation_jobs(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_media_jobs_external ON media_generation_jobs(provider, external_job_id);
        CREATE INDEX IF NOT EXISTS ix_media_jobs_status ON media_generation_jobs(status, next_poll_at);
        """,
    ),

    (
        "019_v31_provider_resilience",
        """
        CREATE TABLE IF NOT EXISTS provider_circuit_states (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            service VARCHAR(100) NOT NULL,
            provider VARCHAR(100) NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'CLOSED',
            failure_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            opened_at TIMESTAMP NULL,
            next_probe_at TIMESTAMP NULL,
            half_open_until TIMESTAMP NULL,
            last_failure_at TIMESTAMP NULL,
            last_success_at TIMESTAMP NULL,
            last_error TEXT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_provider_circuit_portfolio_service_provider UNIQUE (portfolio_id, service, provider)
        );
        CREATE INDEX IF NOT EXISTS ix_provider_circuit_state ON provider_circuit_states(state, next_probe_at);

        CREATE TABLE IF NOT EXISTS workflow_dead_letters (
            id UUID PRIMARY KEY,
            workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            reason TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP NULL,
            resolution TEXT NULL,
            CONSTRAINT uq_workflow_dead_letters_run UNIQUE (workflow_run_id)
        );
        CREATE INDEX IF NOT EXISTS ix_workflow_dead_letters_created ON workflow_dead_letters(created_at);

        ALTER TABLE media_generation_jobs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255);
        ALTER TABLE media_generation_jobs ADD COLUMN IF NOT EXISTS local_output_path TEXT;
        ALTER TABLE media_generation_jobs ADD COLUMN IF NOT EXISTS portfolio_id UUID NULL REFERENCES portfolios(id) ON DELETE SET NULL;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'uq_media_generation_jobs_idempotency_key'
            ) THEN
                ALTER TABLE media_generation_jobs ADD CONSTRAINT uq_media_generation_jobs_idempotency_key UNIQUE (idempotency_key);
            END IF;
        END $$;
        """,
    ),
    ("020_v32_quality_postpublish", """
        CREATE TABLE IF NOT EXISTS video_quality_reports (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            portfolio_id UUID NULL REFERENCES portfolios(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            stage VARCHAR(50) NOT NULL DEFAULT 'pre_publish',
            status VARCHAR(20) NOT NULL DEFAULT 'PASS',
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            checks JSONB NOT NULL DEFAULT '{}'::jsonb,
            issues JSONB NOT NULL DEFAULT '[]'::jsonb,
            recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_video_quality_reports_project_created ON video_quality_reports(project_id, created_at);

        CREATE TABLE IF NOT EXISTS post_publish_monitors (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            portfolio_id UUID NULL REFERENCES portfolios(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            youtube_video_id VARCHAR(128) NOT NULL,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            baseline_days INTEGER NOT NULL DEFAULT 28,
            anomaly_threshold_pct DOUBLE PRECISION NOT NULL DEFAULT 20,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            auto_correct BOOLEAN NOT NULL DEFAULT FALSE,
            next_check_at TIMESTAMP NOT NULL,
            last_checked_at TIMESTAMP NULL,
            last_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
            checks_count INTEGER NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_post_publish_monitors_due ON post_publish_monitors(enabled, next_check_at);
        CREATE INDEX IF NOT EXISTS ix_post_publish_monitors_channel_video ON post_publish_monitors(channel_id, youtube_video_id);

        CREATE TABLE IF NOT EXISTS performance_alerts (
            id UUID PRIMARY KEY,
            monitor_id UUID NOT NULL REFERENCES post_publish_monitors(id) ON DELETE CASCADE,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            youtube_video_id VARCHAR(128) NOT NULL,
            dedupe_key VARCHAR(255) NOT NULL UNIQUE,
            alert_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL DEFAULT 'medium',
            metric VARCHAR(80) NOT NULL,
            current_value DOUBLE PRECISION NOT NULL DEFAULT 0,
            baseline_value DOUBLE PRECISION NOT NULL DEFAULT 0,
            delta_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            remediation JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP NULL
        );
        CREATE INDEX IF NOT EXISTS ix_performance_alerts_monitor_status ON performance_alerts(monitor_id, status, created_at);
        CREATE INDEX IF NOT EXISTS ix_performance_alerts_channel_status ON performance_alerts(channel_id, status, created_at);
    """),
    ("021_v33_content_evolution", """
        ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS content_root_id UUID NULL;
        ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS parent_project_id UUID NULL;
        ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS revision_number INTEGER NOT NULL DEFAULT 0;
        DO $$ BEGIN
            ALTER TABLE video_projects ADD CONSTRAINT fk_video_projects_content_root FOREIGN KEY (content_root_id) REFERENCES video_projects(id) ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
            ALTER TABLE video_projects ADD CONSTRAINT fk_video_projects_parent_project FOREIGN KEY (parent_project_id) REFERENCES video_projects(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        UPDATE video_projects SET content_root_id = id WHERE content_root_id IS NULL;
        CREATE INDEX IF NOT EXISTS ix_video_projects_content_root ON video_projects(content_root_id);
        CREATE INDEX IF NOT EXISTS ix_video_projects_parent_project ON video_projects(parent_project_id);
        CREATE INDEX IF NOT EXISTS ix_video_projects_revision ON video_projects(content_root_id, revision_number);
        DO $$ BEGIN
            ALTER TABLE video_projects ADD CONSTRAINT uq_video_projects_root_revision UNIQUE(content_root_id, revision_number);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        CREATE TABLE IF NOT EXISTS content_versions (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            content_root_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            parent_project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            revision_number INTEGER NOT NULL DEFAULT 0,
            trigger_type VARCHAR(40) NOT NULL DEFAULT 'baseline',
            trigger_alert_id UUID NULL REFERENCES performance_alerts(id) ON DELETE SET NULL,
            reason TEXT NOT NULL DEFAULT '',
            change_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_content_versions_root_revision UNIQUE(content_root_id, revision_number),
            CONSTRAINT uq_content_versions_trigger_alert UNIQUE(trigger_alert_id)
        );
        CREATE INDEX IF NOT EXISTS ix_content_versions_project_created ON content_versions(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_content_versions_parent ON content_versions(parent_project_id);

        CREATE TABLE IF NOT EXISTS content_artifacts (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            artifact_type VARCHAR(40) NOT NULL,
            relative_path TEXT NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            size_bytes BIGINT NOT NULL DEFAULT 0,
            immutable BOOLEAN NOT NULL DEFAULT TRUE,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_content_artifact_identity UNIQUE(project_id, artifact_type, relative_path)
        );
        CREATE INDEX IF NOT EXISTS ix_content_artifacts_project_type ON content_artifacts(project_id, artifact_type);
        CREATE INDEX IF NOT EXISTS ix_content_artifacts_sha256 ON content_artifacts(sha256);

        CREATE OR REPLACE FUNCTION set_content_root_and_baseline() RETURNS trigger AS $$
        BEGIN
            IF NEW.content_root_id IS NULL THEN
                NEW.content_root_id := NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS trg_video_projects_content_root ON video_projects;
        CREATE TRIGGER trg_video_projects_content_root
        BEFORE INSERT ON video_projects
        FOR EACH ROW EXECUTE FUNCTION set_content_root_and_baseline();

        CREATE OR REPLACE FUNCTION ensure_content_version_baseline() RETURNS trigger AS $$
        BEGIN
            IF NEW.revision_number = 0 THEN
                INSERT INTO content_versions(id, project_id, content_root_id, parent_project_id, revision_number, trigger_type, reason, status)
                VALUES (NEW.id, NEW.id, NEW.content_root_id, NEW.parent_project_id, NEW.revision_number, 'baseline', '', 'BASELINE')
                ON CONFLICT (content_root_id, revision_number) DO NOTHING;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS trg_video_projects_baseline_version ON video_projects;
        CREATE TRIGGER trg_video_projects_baseline_version
        AFTER INSERT ON video_projects
        FOR EACH ROW EXECUTE FUNCTION ensure_content_version_baseline();

        INSERT INTO content_versions(id, project_id, content_root_id, parent_project_id, revision_number, trigger_type, reason, status)
        SELECT id, id, COALESCE(content_root_id, id), parent_project_id, revision_number, 'baseline', '', 'BASELINE'
        FROM video_projects
        ON CONFLICT (content_root_id, revision_number) DO NOTHING;
    """),
    (
        "022_v34_creative_intelligence",
        """
        CREATE TABLE IF NOT EXISTS creative_analyses (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            stage VARCHAR(40) NOT NULL DEFAULT 'post_render',
            status VARCHAR(20) NOT NULL DEFAULT 'PASS',
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            sampled_frames INTEGER NOT NULL DEFAULT 0,
            scene_reports JSONB NOT NULL DEFAULT '[]'::jsonb,
            audio_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
            visual_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
            issues JSONB NOT NULL DEFAULT '[]'::jsonb,
            recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
            reedit_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_creative_analyses_project_created ON creative_analyses(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_creative_analyses_channel_status ON creative_analyses(channel_id, status);
        """,
    ),
    (
        "023_v35_creative_director",
        """
        CREATE TABLE IF NOT EXISTS creative_director_decisions (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            analysis_id UUID NULL REFERENCES creative_analyses(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'READY',
            max_changes INTEGER NOT NULL DEFAULT 3,
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            plan JSONB NOT NULL DEFAULT '{}'::jsonb,
            execution_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_creative_director_project_created ON creative_director_decisions(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_creative_director_project_status ON creative_director_decisions(project_id, status);
        CREATE INDEX IF NOT EXISTS ix_creative_director_analysis ON creative_director_decisions(analysis_id);
        """,
    ),
    (
        "024_v36_multimodal_production_graph",
        """
        CREATE TABLE IF NOT EXISTS production_multimodal_graphs (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            stage VARCHAR(30) NOT NULL DEFAULT 'pre_render',
            status VARCHAR(20) NOT NULL DEFAULT 'PASS',
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',
            nodes JSONB NOT NULL DEFAULT '[]'::jsonb,
            edges JSONB NOT NULL DEFAULT '[]'::jsonb,
            conflicts JSONB NOT NULL DEFAULT '[]'::jsonb,
            recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
            signals JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_multimodal_graphs_project_created ON production_multimodal_graphs(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_multimodal_graphs_channel_stage ON production_multimodal_graphs(channel_id, stage);
        """,
    ),
    (
        "025_v37_autonomous_optimization",
        """
        CREATE TABLE IF NOT EXISTS autonomous_optimization_decisions (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            source_alert_id UUID NULL REFERENCES performance_alerts(id) ON DELETE SET NULL,
            target_scope VARCHAR(40) NOT NULL DEFAULT 'no_action',
            priority DOUBLE PRECISION NOT NULL DEFAULT 0,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'PROPOSED',
            hypothesis TEXT NOT NULL DEFAULT '',
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            action_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
            guardrails JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_auto_opt_alert_org UNIQUE (organization_id, source_alert_id)
        );
        CREATE INDEX IF NOT EXISTS ix_auto_opt_project_created ON autonomous_optimization_decisions(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_auto_opt_channel_status ON autonomous_optimization_decisions(channel_id, status);
        """,
    ),
    (
        "026_v38_autonomous_execution_controller",
        """
        CREATE TABLE IF NOT EXISTS autonomous_execution_runs (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
            decision_id UUID NOT NULL REFERENCES autonomous_optimization_decisions(id) ON DELETE CASCADE,
            workflow_id UUID NULL REFERENCES workflow_runs(id) ON DELETE SET NULL,
            revision_project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            experiment_id UUID NULL REFERENCES content_experiments(id) ON DELETE SET NULL,
            reservation_id UUID NULL REFERENCES budget_reservations(id) ON DELETE SET NULL,
            mode VARCHAR(20) NOT NULL DEFAULT 'approve',
            status VARCHAR(30) NOT NULL DEFAULT 'APPROVAL_REQUIRED',
            idempotency_key VARCHAR(255) NOT NULL,
            target_scope VARCHAR(40) NOT NULL,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            requested_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            reason TEXT NOT NULL DEFAULT '',
            guardrails JSONB NOT NULL DEFAULT '[]'::jsonb,
            result JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            CONSTRAINT uq_execution_decision_idempotency UNIQUE(decision_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_execution_org_status ON autonomous_execution_runs(organization_id, status);
        CREATE INDEX IF NOT EXISTS ix_execution_project_created ON autonomous_execution_runs(project_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_execution_workflow ON autonomous_execution_runs(workflow_id);
        """,
    ),
    (
        "027_v39_agent_governance_human_oversight",
        """
        CREATE TABLE IF NOT EXISTS agent_governance_policies (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL UNIQUE REFERENCES channels(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            emergency_kill_switch BOOLEAN NOT NULL DEFAULT FALSE,
            default_mode VARCHAR(20) NOT NULL DEFAULT 'approve',
            approval_timeout_minutes INTEGER NOT NULL DEFAULT 120,
            policy_version INTEGER NOT NULL DEFAULT 1,
            automation_policies JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_governance_kill_switch ON agent_governance_policies(emergency_kill_switch);

        CREATE TABLE IF NOT EXISTS agent_action_policies (
            id UUID PRIMARY KEY,
            governance_policy_id UUID NOT NULL REFERENCES agent_governance_policies(id) ON DELETE CASCADE,
            action_type VARCHAR(60) NOT NULL,
            risk_tier VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
            automation_mode VARCHAR(20) NOT NULL DEFAULT 'approve',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            require_human_approval BOOLEAN NOT NULL DEFAULT TRUE,
            max_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.60,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_action_policy_action UNIQUE(governance_policy_id, action_type)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_action_policy_type ON agent_action_policies(action_type, enabled);

        CREATE TABLE IF NOT EXISTS agent_approval_requests (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            execution_run_id UUID NOT NULL UNIQUE REFERENCES autonomous_execution_runs(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NULL,
            decided_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMP NULL,
            decision_reason TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_agent_approval_channel_status ON agent_approval_requests(channel_id, status);

        CREATE TABLE IF NOT EXISTS agent_governance_events (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            execution_run_id UUID NULL REFERENCES autonomous_execution_runs(id) ON DELETE SET NULL,
            decision_id UUID NULL REFERENCES autonomous_optimization_decisions(id) ON DELETE SET NULL,
            action_type VARCHAR(60) NOT NULL,
            risk_tier VARCHAR(20) NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            allowed BOOLEAN NOT NULL DEFAULT FALSE,
            effective_mode VARCHAR(20) NOT NULL,
            policy_version INTEGER NOT NULL DEFAULT 1,
            reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
            actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_governance_event_channel_created ON agent_governance_events(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_agent_governance_event_run_created ON agent_governance_events(execution_run_id, created_at);
        """,
    ),
    (
        "028_v40_multi_agent_runtime",
        """
        CREATE TABLE IF NOT EXISTS agent_definitions (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NULL REFERENCES channels(id) ON DELETE CASCADE,
            agent_key VARCHAR(80) NOT NULL,
            display_name VARCHAR(160) NOT NULL,
            capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            max_concurrency INTEGER NOT NULL DEFAULT 1,
            default_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_definition_org_key UNIQUE(organization_id, agent_key)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_definition_channel ON agent_definitions(channel_id, enabled);

        CREATE TABLE IF NOT EXISTS agent_tasks (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            parent_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
            agent_key VARCHAR(80) NOT NULL,
            task_type VARCHAR(80) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
            priority INTEGER NOT NULL DEFAULT 50,
            requested_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            reserved_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            actual_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            idempotency_key VARCHAR(255) NOT NULL,
            input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP NULL,
            completed_at TIMESTAMP NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_task_channel_idempotency UNIQUE(channel_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_task_channel_status ON agent_tasks(channel_id, status, priority);
        CREATE INDEX IF NOT EXISTS ix_agent_task_parent ON agent_tasks(parent_task_id);

        CREATE TABLE IF NOT EXISTS agent_task_dependencies (
            id UUID PRIMARY KEY, task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            depends_on_task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_task_dependency UNIQUE(task_id, depends_on_task_id)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_dependency_task ON agent_task_dependencies(task_id);

        CREATE TABLE IF NOT EXISTS agent_leases (
            id UUID PRIMARY KEY, task_id UUID NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE CASCADE,
            agent_key VARCHAR(80) NOT NULL, lease_token VARCHAR(255) NOT NULL UNIQUE,
            acquired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, heartbeat_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_agent_lease_agent_active ON agent_leases(agent_key, expires_at);

        CREATE TABLE IF NOT EXISTS agent_handoffs (
            id UUID PRIMARY KEY, task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            from_agent VARCHAR(80) NOT NULL, to_agent VARCHAR(80) NOT NULL, handoff_type VARCHAR(50) NOT NULL DEFAULT 'DELEGATE',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb, reason TEXT NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_handoff_task_created ON agent_handoffs(task_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_budget_ledger (
            id UUID PRIMARY KEY, organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE, task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
            agent_key VARCHAR(80) NOT NULL, entry_type VARCHAR(30) NOT NULL, amount_usd DOUBLE PRECISION NOT NULL,
            balance_after_usd DOUBLE PRECISION NOT NULL DEFAULT 0, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_budget_channel_created ON agent_budget_ledger(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_agent_budget_task ON agent_budget_ledger(task_id);
        """,
    ),
    (
        "029_v41_agent_planner_dynamic_workflow_graph",
        """
        CREATE TABLE IF NOT EXISTS agent_plans (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            project_id UUID NULL REFERENCES video_projects(id) ON DELETE SET NULL,
            parent_plan_id UUID NULL REFERENCES agent_plans(id) ON DELETE SET NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
            goal TEXT NOT NULL,
            plan_version INTEGER NOT NULL DEFAULT 1,
            replan_count INTEGER NOT NULL DEFAULT 0,
            budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            strategy JSONB NOT NULL DEFAULT '{}'::jsonb,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            governance_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            rationale JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_plan_channel_status ON agent_plans(channel_id, status, created_at);

        CREATE TABLE IF NOT EXISTS agent_plan_nodes (
            id UUID PRIMARY KEY,
            plan_id UUID NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE,
            node_key VARCHAR(100) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
            requested_capability VARCHAR(100) NOT NULL,
            agent_key VARCHAR(80) NOT NULL,
            task_type VARCHAR(80) NOT NULL,
            action_type VARCHAR(80) NOT NULL,
            estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            governance_mode VARCHAR(20) NOT NULL DEFAULT 'block',
            rationale TEXT NOT NULL DEFAULT '',
            input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_plan_node_key UNIQUE(plan_id, node_key)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_plan_node_plan_status ON agent_plan_nodes(plan_id, status);

        CREATE TABLE IF NOT EXISTS agent_plan_edges (
            id UUID PRIMARY KEY,
            plan_id UUID NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE,
            from_node_id UUID NOT NULL REFERENCES agent_plan_nodes(id) ON DELETE CASCADE,
            to_node_id UUID NOT NULL REFERENCES agent_plan_nodes(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_plan_edge UNIQUE(from_node_id, to_node_id)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_plan_edge_to ON agent_plan_edges(to_node_id);
        """,
    ),
    (
        "030_v42_agent_learning_self_improvement",
        """
        CREATE TABLE IF NOT EXISTS agent_learning_observations (
            id UUID PRIMARY KEY, organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
            execution_run_id UUID NULL REFERENCES autonomous_execution_runs(id) ON DELETE SET NULL,
            plan_id UUID NULL REFERENCES agent_plans(id) ON DELETE SET NULL,
            agent_key VARCHAR(80) NOT NULL, action_type VARCHAR(80) NOT NULL, outcome VARCHAR(30) NOT NULL,
            success BOOLEAN NOT NULL DEFAULT FALSE, reward DOUBLE PRECISION NULL, cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
            latency_ms DOUBLE PRECISION NULL, metrics JSONB NOT NULL DEFAULT '{}'::jsonb, context JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_learning_obs_channel_idempotency UNIQUE(channel_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_learning_obs_channel_created ON agent_learning_observations(channel_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_agent_learning_obs_task ON agent_learning_observations(task_id);

        CREATE TABLE IF NOT EXISTS agent_learning_evaluations (
            id UUID PRIMARY KEY, organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE, observation_id UUID NOT NULL REFERENCES agent_learning_observations(id) ON DELETE CASCADE,
            score DOUBLE PRECISION NOT NULL DEFAULT 0, confidence DOUBLE PRECISION NOT NULL DEFAULT 0, evaluator VARCHAR(80) NOT NULL DEFAULT 'deterministic',
            rationale JSONB NOT NULL DEFAULT '[]'::jsonb, evidence JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_learning_eval_channel_created ON agent_learning_evaluations(channel_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_strategy_proposals (
            id UUID PRIMARY KEY, organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE, agent_key VARCHAR(80) NOT NULL,
            source_observation_ids JSONB NOT NULL DEFAULT '[]'::jsonb, source_evaluation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(30) NOT NULL DEFAULT 'PENDING_APPROVAL', proposed_changes JSONB NOT NULL DEFAULT '{}'::jsonb,
            expected_impact JSONB NOT NULL DEFAULT '{}'::jsonb, rationale JSONB NOT NULL DEFAULT '[]'::jsonb,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0, requires_human_approval BOOLEAN NOT NULL DEFAULT TRUE,
            approved_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL, decided_at TIMESTAMP NULL, decision_reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_strategy_proposal_channel_status ON agent_strategy_proposals(channel_id, status, created_at);

        CREATE TABLE IF NOT EXISTS agent_strategy_versions (
            id UUID PRIMARY KEY, organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE, agent_key VARCHAR(80) NOT NULL, version INTEGER NOT NULL,
            source_proposal_id UUID NULL REFERENCES agent_strategy_proposals(id) ON DELETE SET NULL, strategy JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT FALSE, activated_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            activated_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_agent_strategy_version UNIQUE(channel_id, agent_key, version)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_strategy_active ON agent_strategy_versions(channel_id, agent_key, active);
        """,
    ),
    (
        "031_v421_agent_control_plane_correction",
        """
        ALTER TABLE agent_definitions DROP CONSTRAINT IF EXISTS uq_agent_definition_org_key;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_definition_channel_key_idx ON agent_definitions(channel_id, agent_key);

        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS plan_node_id UUID NULL REFERENCES agent_plan_nodes(id) ON DELETE SET NULL;
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS workflow_run_id UUID NULL REFERENCES workflow_runs(id) ON DELETE SET NULL;
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS action_type VARCHAR(80) NOT NULL DEFAULT 'unknown';
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS risk_tier VARCHAR(20) NOT NULL DEFAULT 'CRITICAL';
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS governance_mode VARCHAR(20) NOT NULL DEFAULT 'block';
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS governance_approved BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0;
        ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS governance_policy_version INTEGER NOT NULL DEFAULT 1;
        CREATE INDEX IF NOT EXISTS ix_agent_task_plan_node ON agent_tasks(plan_node_id);
        CREATE INDEX IF NOT EXISTS ix_agent_task_workflow ON agent_tasks(workflow_run_id);

        ALTER TABLE agent_task_dependencies DROP CONSTRAINT IF EXISTS ck_agent_dependency_not_self;
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_agent_dependency_not_self'
            ) THEN
                ALTER TABLE agent_task_dependencies
                ADD CONSTRAINT ck_agent_dependency_not_self CHECK (task_id <> depends_on_task_id);
            END IF;
        END $$;

        ALTER TABLE agent_approval_requests ALTER COLUMN execution_run_id DROP NOT NULL;
        ALTER TABLE agent_approval_requests ADD COLUMN IF NOT EXISTS agent_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE CASCADE;
        ALTER TABLE agent_approval_requests DROP CONSTRAINT IF EXISTS uq_agent_approval_execution;
        DROP INDEX IF EXISTS uq_agent_approval_execution_idx;
        CREATE INDEX IF NOT EXISTS ix_agent_approval_run_status ON agent_approval_requests(execution_run_id, status);
        CREATE INDEX IF NOT EXISTS ix_agent_approval_task ON agent_approval_requests(agent_task_id);
        ALTER TABLE agent_approval_requests DROP CONSTRAINT IF EXISTS uq_agent_approval_task;
        DROP INDEX IF EXISTS uq_agent_approval_task_idx;
        CREATE INDEX IF NOT EXISTS ix_agent_approval_task_status ON agent_approval_requests(agent_task_id, status);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_approval_pending_run_idx ON agent_approval_requests(execution_run_id) WHERE execution_run_id IS NOT NULL AND status = 'PENDING';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_approval_pending_task_idx ON agent_approval_requests(agent_task_id) WHERE agent_task_id IS NOT NULL AND status = 'PENDING';
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_agent_approval_target'
            ) THEN
                ALTER TABLE agent_approval_requests
                ADD CONSTRAINT ck_agent_approval_target CHECK ((execution_run_id IS NOT NULL) <> (agent_task_id IS NOT NULL));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_agent_approval_status'
            ) THEN
                ALTER TABLE agent_approval_requests
                ADD CONSTRAINT ck_agent_approval_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'SUPERSEDED'));
            END IF;
        END $$;

        ALTER TABLE agent_governance_events ADD COLUMN IF NOT EXISTS agent_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_agent_governance_event_task_created ON agent_governance_events(agent_task_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_plan_events (
            id UUID PRIMARY KEY,
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE SET NULL,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            plan_id UUID NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE,
            plan_version INTEGER NOT NULL DEFAULT 1,
            event_type VARCHAR(50) NOT NULL,
            node_key VARCHAR(100) NULL,
            actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_agent_plan_event_plan_created ON agent_plan_events(plan_id, created_at);

        ALTER TABLE agent_plan_nodes ADD COLUMN IF NOT EXISTS risk_tier VARCHAR(20) NOT NULL DEFAULT 'CRITICAL';
        ALTER TABLE agent_plan_nodes ADD COLUMN IF NOT EXISTS governance_policy_version INTEGER NOT NULL DEFAULT 1;

        ALTER TABLE agent_learning_observations ADD COLUMN IF NOT EXISTS source_type VARCHAR(30) NOT NULL DEFAULT 'agent_task';
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_agent_learning_evaluation_observation'
            ) THEN
                ALTER TABLE agent_learning_evaluations
                ADD CONSTRAINT uq_agent_learning_evaluation_observation UNIQUE(observation_id);
            END IF;
        END $$;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_strategy_active_idx ON agent_strategy_versions(channel_id, agent_key) WHERE active = TRUE;
        ALTER TABLE agent_strategy_proposals ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP NULL;
        """,
    ),
    (
        "032_v421_lease_tenant_columns",
        """
        ALTER TABLE agent_leases ADD COLUMN IF NOT EXISTS channel_id UUID NULL REFERENCES channels(id) ON DELETE CASCADE;
        UPDATE agent_leases SET channel_id = (SELECT t.channel_id FROM agent_tasks t WHERE t.id = agent_leases.task_id) WHERE channel_id IS NULL;
        ALTER TABLE agent_leases ALTER COLUMN channel_id SET NOT NULL;
        CREATE INDEX IF NOT EXISTS ix_agent_lease_channel ON agent_leases(channel_id);
        """,
    ),
    (
        "033_security_function_search_path",
        """
        ALTER FUNCTION public.ensure_content_version_baseline() SET search_path = public, pg_temp;
        ALTER FUNCTION public.set_content_root_and_baseline() SET search_path = public, pg_temp;
        """,
    ),
    (
        "034_lock_public_data_api_roles",
        """
        REVOKE ALL ON SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
        """,
    ),
    (
        "035_enforce_content_version_json_defaults",
        """
        ALTER TABLE content_versions
            ALTER COLUMN change_plan SET DEFAULT '{}'::jsonb,
            ALTER COLUMN metrics_snapshot SET DEFAULT '{}'::jsonb;
        UPDATE content_versions
        SET change_plan = '{}'::jsonb
        WHERE change_plan IS NULL;
        UPDATE content_versions
        SET metrics_snapshot = '{}'::jsonb
        WHERE metrics_snapshot IS NULL;
        ALTER TABLE content_versions
            ALTER COLUMN change_plan SET NOT NULL,
            ALTER COLUMN metrics_snapshot SET NOT NULL;
        """,
    ),
    (
        "036_enforce_content_version_timestamps",
        """
        ALTER TABLE content_versions
            ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;
        UPDATE content_versions
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL;
        UPDATE content_versions
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL;
        ALTER TABLE content_versions
            ALTER COLUMN created_at SET NOT NULL,
            ALTER COLUMN updated_at SET NOT NULL;
        """,
    ),]


def _split_sql(sql: str) -> list[str]:
    """Split top-level PostgreSQL statements without breaking dollar-quoted DO blocks."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue
        if dollar_tag:
            if sql.startswith(dollar_tag, i):
                buf.extend(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
            else:
                buf.append(ch)
                i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                if nxt == '"':
                    buf.append(nxt)
                    i += 2
                    continue
                in_double = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf.extend((ch, nxt))
            i += 2
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            buf.extend((ch, nxt))
            i += 2
            in_block_comment = True
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            import re
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if match:
                dollar_tag = match.group(0)
                buf.extend(dollar_tag)
                i += len(dollar_tag)
                continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


async def apply_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        # Serialize schema changes across concurrent API/worker startups.
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('youtube_ai_platform_schema_migrations'))"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        for version, sql in MIGRATIONS:
            exists = await conn.execute(text("SELECT 1 FROM schema_migrations WHERE version=:version"), {"version": version})
            if exists.scalar_one_or_none():
                continue
            for statement in _split_sql(sql):
                await conn.execute(text(statement))
            await conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:version)"), {"version": version})

