# Текущий аудит AI-Youtube

Дата проверки: 2026-09-24. Проверена рабочая копия `worktrees/youtube-connect-toggle`.

## Состояние репозитория

- Remote `origin`: `https://github.com/demoon555ee-coder/AI-Youtube.git`.
- Ветка: `main`.
- HEAD: `17615cb58d024d21065482c5e22eff24e6f23e7f`, совпадает с локальным `origin/main`.
- По истории последние изменения включают Welcome/Auth, Google OAuth state, PostgreSQL credentials и Connect/Disconnect YouTube.
- Старая рабочая копия в Downloads существует как отдельная worktree/ветка; она не использовалась.
- В Git-истории обнаружены credential-like Google OAuth/API значения в `.env`, `token.json`, `credentials.json` и pipeline logs под старым remote-tracking ref `origin/autonomous-ai-channel-on-youtube-f6b58`. Эти коммиты не являются предками текущего `main`; remote считает ref stale. Значения не выводились. Это всё равно требует считать найденные ключи/токены раскрытыми и оценить ротацию.
- До правок локальные `.env`, `secrets/client_secret.json` и `__pycache__` отображались Git как untracked. Добавлен корневой `.gitignore`, сохраняющий `*.example` файлы.
- До обновления локальной среды API image был старше исходников и возвращал HTTP 500 на OpenAPI; после правки стек пересобран и этот endpoint отвечает HTTP 200.

## Карта системы

```text
Next.js UI (frontend/app, frontend/components, frontend/lib/api.ts)
  → FastAPI routers (app/api, app/main.py)
  → auth/resource authorization (app/auth)
  → services + specialized agents (app/services, app/*, app/agents)
  → async SQLAlchemy models + PostgreSQL (app/models, app/db)
  → durable workflow worker / agent task worker (app/workflows)
  → external Google, YouTube, AI and media providers
```

- Frontend: Next.js 15/React 19; общий `frontend/lib/api.ts` передаёт cookie, запрашивает CSRF token и добавляет его к изменяющим запросам. Активный workspace хранится в `localStorage` (`youtube_ai_channel_id`), а не на сервере.
- API: FastAPI, глобальная `enforce_request_authorization`, resource ownership по организации/владельцу, CORS и request/trace IDs. `/openapi.json` был сломан из-за отсутствующего импорта UUID в privacy router; ошибка исправлена и теперь проходит в тесте и живом container.
- Database: PostgreSQL + async SQLAlchemy; базовая схема создаётся через `Base.metadata.create_all`, затем применяется список из 36 идемпотентных SQL migrations с advisory lock.
- Background work: отдельный workflow worker и отдельный AgentTaskWorker. Workflow worker теперь запущен в локальном compose stack. README прямо указывает, что control-plane agent task пока не интегрирован как замена/продолжение renderer workflow.
- Governance: отдельные policy/admission/approval/kill-switch сервисы и durable agent tasks; publish endpoint ставит задачу в governed queue.
- CI: GitHub Actions содержит Python 3.12/3.13, frontend build, PostgreSQL 15/16 integration, staging Docker/Remotion smoke/browser E2E и release audit. Production deployment — отдельный ручной workflow с digest-pinned images.

## Матрица функций

| Функция | Статус | Основные файлы | Проверки | Примечания |
|---|---|---|---|---|
| Google authentication | PARTIAL / live flow untested | `app/services/google_auth.py`, `app/api/auth.py`, `frontend/app/login/page.tsx` | `tests/test_v43_google_onboarding.py`, `tests/test_youtube_oauth.py` | Реальные Google endpoints, state, ID-token verification и session cookie есть. В браузере ввод email дошёл до запроса пароля; callback и выдача сессии этим не подтверждены. |
| Google → реальные YouTube channels | PARTIAL / live API untested | `app/services/youtube_client.py`, `app/api/auth.py`, `frontend/app/onboarding/channels/page.tsx` | `tests/test_v43_google_onboarding.py` | Вызывается `channels.list(mine=true)`, не выдумывается YouTube ID; доступные каналы связываются с workspace. Нет подтверждённого входа с реальным аккаунтом в этой проверке. |
| Channel/workspace selection | PARTIAL | `app/api/routes.py`, `frontend/app/onboarding/channels/page.tsx`, `frontend/lib/api.ts`, `frontend/components/Shell.tsx` | `tests/test_route_ownership.py`, frontend E2E source | Выбор сохраняется в браузере и проверяется по списку доступных каналов после reload; нет серверного active-channel preference. |
| YouTube connect/disconnect | PARTIAL / live API untested | `app/api/youtube.py`, `app/services/youtube_service.py`, `frontend/app/settings/page.tsx` | OAuth/route contract tests | Connection хранится отдельно от Channel; disconnect удаляет только `YouTubeConnection`, пишет audit и сохраняет workspace/channel. |
| YouTube upload/publish | REAL implementation / untested against Google | `app/services/youtube_client.py`, `app/services/youtube_service.py`, `app/api/youtube.py`, `app/agents/publisher.py` | `tests/test_youtube_upload_contract.py` | Реализован resumable `videos.insert`, thumbnail upload и governed publisher task. Контрактный тест использует fake API; реальная публикация не проверена. |
| YouTube Analytics | REAL implementation / untested against Google | `app/services/youtube_client.py`, `app/services/youtube_service.py`, `app/services/analytics_store.py` | unit/provider contracts | Реализован `youtubeAnalytics.reports().query` и сохранение строк. Реальные отчёты, доступы и ограничения квот не проверены. |
| LLM/research/image/vision/TTS/video providers | PARTIAL, environment-dependent | `app/providers`, `app/research`, `app/media`, `app/vision`, `app/tts`, `app/config.py` | provider contract tests | Текущий локальный `.env` выбирает OpenAI-compatible LLM, YouTube Data API research, OpenAI chat vision и Stability image; TTS — eSpeak, video — `mock_video`. Наличие ключей/успешность запросов не проверялись. Runway, Pexels, ElevenLabs adapters присутствуют, реальный вызов не проверен. |
| Video render / Remotion | PARTIAL | `app/rendering`, `app/remotion`, `app/services/orchestrator.py` | render tests; CI Remotion smoke | FFmpeg — текущий default; Remotion выбирается конфигурацией. Локальный stack работает, но полный сценарий render→QA→publish в нём не запускался. Media providers могут быть mock. |
| Subtitles | PARTIAL | `app/rendering/service.py`, `app/rendering/remotion.py`, `app/remotion/src/Root.tsx` | render tests | SRT/captions создаются из текста storyboard/narration и встраиваются в видео. В рассмотренном pipeline нет ASR-транскрипции итогового аудио и точного word-level alignment. |
| Thumbnails/experiments | PARTIAL | `app/thumbnail/service.py`, `app/experiments/engine.py` | thumbnail/experiment tests | Pillow собирает варианты; можно передать реальный image provider. Само наличие вариантов не подтверждает полноценный YouTube A/B эксперимент или причинно-обоснованный CTR lift. |
| Research/analytics learning loop | PARTIAL | `app/research`, `app/brain`, `app/postpublish`, `app/learning`, `app/evolution` | многочисленные unit/contract tests | Сервисы и таблицы для research, analytics snapshots, monitoring и bounded learning существуют. Внешние реальные данные и весь цикл до следующего видео не проверены end-to-end. |
| Governance/approvals/emergency stop | REAL architecture / runtime unverified | `app/governance`, `app/api/governance.py`, `app/runtime`, `app/execution` | governance/runtime tests | Централизованная admission, риск, approval, kill switch и lease-based tasks существуют. Production-политики/живое выполнение не проверялись. |
| Durable content workflow | PARTIAL integration | `app/workflows`, `app/services/orchestrator.py`, `app/agents` | workflow tests; E2E source | Durable workflow и retry/checkpoint контракты реализованы; отдельный agent control plane пока не управляет всем production renderer pipeline (см. README). |
| Local PostgreSQL migration gate | VERIFIED on existing dev DB and fresh staging DB | `docker-compose.yml`, `docker-compose.staging.yml`, `scripts/migrate.py` | compose contract tests + successful fresh staging startup | Мигратор завершился с кодом 0 до API/worker; staging DB была новой в отдельном project/volume, readiness подтверждает актуальную schema. |
| Secret/cache ignore | FIXED IN THIS CHANGE | `.gitignore` | Git ignore/status checks | Исключены локальные `.env`, `secrets/`, Python caches и обычные frontend/build outputs; environment example files остаются в Git.

## Приоритетные gaps

### P0

1. **Credential rotation требуется.** Во время предыдущей проверки локальный OAuth client secret попал в вывод; кроме того, сканирование Git history нашло Google OAuth client/access tokens и Google API key в старых commits старой/stale ветки (не предках текущего `main`). Текущие значения не показывались и не менялись. По инструкции пользователя credential не отзываются автоматически; владелец должен rotate/revoke затронутые credentials и проверить Google Cloud/Railway secrets. После ротации отдельно решить вопрос очистки истории: force-push/rewrite history не выполнялся.
### P1

- Исправить OAuth branding: страница Google показывала `GOOGLE_CLIENT_ID` как название приложения; такой текст не найден в репозитории и меняется в Google Cloud OAuth branding.
- Выполнить browser E2E полного Google login → callback → session → real channels → choose → reload → disconnect/reconnect с владельцем аккаунта. Пароль и финальное согласие Google остаются действием владельца аккаунта; живые Google API calls не подтверждены.
- Связать durable AgentTask/control plane с production WorkflowEngine/renderer в одной наблюдаемой цепочке; сейчас эти системы имеют явную интеграционную границу.
- Подтвердить реальные provider credentials/readiness, YouTube quotas, analytics, upload и publishing на тестовом канале.

### P2

- Ввести server-side active-channel preference или общий validated channel context; сейчас выбор браузерный и каждая страница самостоятельно передаёт channel ID.
- Добавить реальную транскрипцию итогового audio/video и точное согласование субтитров.
- Замкнуть thumbnail experiment → достоверные YouTube observations → bounded optimization; не выдавать статические варианты за измеренный A/B результат.
- Проверить worker health/heartbeat и фактическую конфигурацию production release по текущему commit. `docs/FINAL_PRODUCTION_READINESS.md` ссылается на `0641dc8`, тогда как локальный `main` сейчас на `17615cb`; старый текст документа нельзя считать доказательством текущего деплоя.

## Изменения этого аудита

- `.gitignore`: добавлены правила для локальных credentials, cache и build output; существующие пользовательские файлы не удалялись.
- `docker-compose.yml`: добавлен одноразовый `migrate` service на базе существующего `scripts/migrate.py`; API/worker стартуют только после успешной миграции и не выполняют её параллельно.
- `docker-compose.staging.yml`: web явно слушает на `0.0.0.0`, worker не наследует неподходящий API HTTP healthcheck.
- `e2e/tests/app.spec.ts`, `e2e/playwright.config.ts`: creator flow использует актуальный onboarding для AI workspace без fake YouTube channel и даёт до 5 минут на полный render.
- `tests/test_v23_deployment.py`: контракты проверяют local migration gate, OpenAPI schema build, staging web bind и worker healthcheck.
- `app/api/privacy.py`: импортирован используемый endpoint-аннотацией `UUID`, чтобы FastAPI строил OpenAPI schema.

## Проверка в этой сессии

- Repository/branch/HEAD/remote/worktrees/history: VERIFIED локальными Git-командами; `main` совпадает с локальным `origin/main`.
- Secret scan: VERIFIED без вывода значений; Git-трекинг в текущем `main` содержит только environment examples, а найденные credential-like values находятся в commits старого stale remote ref и не предшествуют текущему `main`.
- Runtime: VERIFIED для обновлённого локального Compose stack — web/API/db healthy; worker запущен; one-shot migrate завершился с кодом 0. `GET /login`, `/onboarding/channels`, `/api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`, `/openapi.json` отвечают 200. Readiness подтверждает database/schema/encryption.
- Fresh database: VERIFIED на отдельной staging DB/volume: PostgreSQL создался с нуля, bootstrap + 36 миграций завершились до API/worker старта; API readiness — ready.
- Login UI: Google button и email form видимы в браузере; create-account toggle переключает форму. При ширинах 390px и 768px горизонтального overflow нет. Ранее Google flow дошёл до запроса пароля; пароль/consent не вводились, полный flow не подтверждён.
- Compose parsing: VERIFIED — `docker compose config --quiet` завершился с кодом 0.
- Local migration compose contract assertions: VERIFIED against Docker Compose resolved config.
- Python compileall: VERIFIED для `app` и новой contract test source.
- `git diff --check`: VERIFIED с кодом 0.
- Docker/runtime: VERIFIED для локальной dev-среды; это не является проверкой production deployment.
- pytest: полный suite — 383 passed, 3 skipped, 1 существующая Pydantic deprecation warning.
- Frontend build: VERIFIED — Next.js 15.5.26 успешно скомпилировал frontend, проверил типы и сгенерировал все 35 статических страниц. Проверка шла на Node 24.19.0 (CI workflow закрепляет Node 22).
- Local staging E2E: VERIFIED — Playwright прошёл регистрацию test user, создание явно обозначенного `Platform workspace`, генерацию идеи/проекта, governance workflow, FFmpeg MP4 rendering и thumbnail (`1 passed`, около 2.1 минуты). Это не проверяет live Google OAuth.
- Responsive login check: VERIFIED без горизонтального overflow при 390px и 768px; браузерный account-create toggle также переключился.
- CI: предыдущий push запуск прошёл backend, frontend, 4 PostgreSQL integration jobs и Remotion smoke; staging browser test выявил устаревший auth assertion и слишком короткий render timeout. Эти причины исправлены, rerun CI для следующего commit будет проверкой итоговой ветки.
