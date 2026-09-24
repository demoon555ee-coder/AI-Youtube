"use client";

import { cloneElement, createContext, Fragment, isValidElement, ReactElement, ReactNode, useContext, useEffect, useState } from "react";

export type Language = "ru" | "en";
const STORAGE_KEY = "youtube_ai_language";

const ru: Record<string, string> = {
  "Dashboard": "Панель управления", "Ideas": "Идеи", "Autopilot": "Автопилот", "Projects": "Проекты",
  "Channel Brain": "Аналитика канала", "Intelligence": "Аналитика", "Portfolio": "Портфель каналов",
  "Portfolio Manager": "Управление портфелем", "Provider Routing": "Маршрутизация провайдеров", "Analytics": "Статистика",
  "Experiments": "Эксперименты", "Research": "Исследования", "Research Scheduler": "Расписание исследований",
  "Trend Intelligence": "Анализ трендов", "Opportunity Intelligence": "Поиск возможностей", "Quality Gate": "Контроль качества",
  "Post-Publish": "После публикации", "Content Evolution": "Развитие контента", "Creative Intelligence": "Креативная аналитика",
  "Creative Director": "Креативный директор", "Autonomous Optimization": "Автоматическая оптимизация", "Billing & Usage": "Тариф и расходы",
  "Privacy Center": "Конфиденциальность", "Settings": "Настройки", "AUTONOMOUS CONTENT OS": "АВТОНОМНАЯ ПЛАТФОРМА ДЛЯ КОНТЕНТА",
  "Change YouTube account or channel": "Сменить аккаунт Google или канал", "Choose channel": "Выберите канал",
  "YouTube workspace": "Рабочее пространство YouTube", "Secure workspace": "Защищённое пространство", "Sign out": "Выйти",
  "Welcome": "Добро пожаловать", "Autonomous creator operating system": "Автономная платформа для авторов",
  "From idea to published video.": "От идеи до готового видео.",
  "Research. Create. Produce. Publish. Learn. One governed workspace for every YouTube channel.": "Исследуйте. Создавайте. Производите. Публикуйте. Учитесь. Единое управляемое пространство для ваших каналов YouTube.",
  "Script": "Сценарий", "Production": "Производство", "Publish": "Публикация", "Learn": "Обучение",
  "Start your studio": "Откройте свою студию", "Create your studio": "Создайте свою студию",
  "Sign in with Google and we will load the YouTube channels available to your account. Then you choose which channel to work with.": "Войдите через Google — мы загрузим доступные вашему аккаунту каналы YouTube, и вы выберете, с каким работать.",
  "Connecting…": "Подключение…", "Continue with Google": "Продолжить с Google", "or": "или",
  "Name": "Имя", "Email": "Электронная почта", "Password": "Пароль", "Workspace name": "Название пространства",
  "Sign in with email": "Войти по почте", "Create account": "Создать аккаунт", "Create a new account": "Создать аккаунт",
  "I already have an account": "У меня уже есть аккаунт", "Google opens the account chooser. After authorization, your available YouTube channels are loaded automatically.": "Google предложит выбрать аккаунт. После авторизации мы автоматически загрузим доступные вам каналы YouTube.",
  "Your YouTube accounts": "Ваши каналы YouTube", "Choose the channel we will operate.": "Выберите канал для работы.",
  "Google is connected. We loaded every YouTube channel available to this account. Pick one to make it the active AI workspace.": "Google подключён. Выберите один из загруженных каналов — он станет активным рабочим пространством.",
  "Google connected. We found ": "Google подключён. Найдено каналов: ", " available channel": " доступный канал", " available channels": " доступных канала",
  "Google connected, but YouTube did not return the channel list. You can create a workspace now or change Google account and try again.": "Google подключён, но YouTube не вернул список каналов. Создайте рабочее пространство или смените аккаунт Google и попробуйте ещё раз.",
  "Selected": "Выбран", "Choose": "Выбрать", "Connected": "Подключён", "YouTube channel": "Канал YouTube",
  "Create a new YouTube channel": "Создать канал YouTube", "Create the channel in YouTube, then bring it into this workspace.": "Создайте канал на YouTube, затем добавьте его в это пространство.",
  "Create a separate AI workspace": "Создать отдельное пространство", "Keep another channel's strategy, projects and governance separate.": "Храните стратегию, проекты и настройки другого канала отдельно.",
  "Change Google account": "Сменить аккаунт Google", "The Google account chooser opens again, then we reload that account's YouTube channels.": "Откроется выбор аккаунта Google, затем мы загрузим каналы выбранного аккаунта.",
  "Continue to Dashboard →": "Перейти к панели управления →", "Workspace setup": "Настройка пространства",
  "Loading your channels…": "Загружаем ваши каналы…", "Preparing your channels…": "Подготавливаем ваши каналы…",
  "Preparing the YouTube accounts available to this Google identity.": "Загружаем каналы YouTube, доступные этому аккаунту Google.",
  "New YouTube channel": "Новый канал YouTube", "Create it in YouTube": "Создайте его на YouTube", "Close": "Закрыть",
  "YouTube creates the actual channel. We only manage the AI workspace and connect it after Google gives us access.": "Сам канал создаётся на YouTube. Здесь настраивается рабочее пространство, а подключить канал можно после выдачи доступа Google.",
  "Open YouTube": "Открыть YouTube", "Create and connect": "Создать и подключить", "New workspace": "Новое пространство",
  "Create a channel workspace": "Создать рабочее пространство канала",
  "This creates a workspace inside the platform. Creating a brand-new YouTube channel itself remains a Google/YouTube action.": "Это создаст рабочее пространство на платформе. Новый канал создаётся отдельно в Google/YouTube.",
  "Niche": "Тематика", "Create workspace": "Создать пространство", "My YouTube Workspace": "Моё пространство YouTube", "AI technology": "Технологии ИИ",
  "Performance intelligence": "Аналитика эффективности", "Overview": "Обзор", "Views": "Просмотры", "Watch time": "Время просмотра",
  "Subscribers": "Подписчики", "Videos": "Видео", "Recent projects": "Последние проекты", "No projects yet.": "Пока нет проектов.",
  "Generate ideas": "Создать идеи", "Generate Ideas": "Создать идеи", "New project": "Новый проект", "Topic": "Тема",
  "Run workflow": "Запустить процесс", "Run AI workflow": "Запустить процесс ИИ", "No projects yet. Generate an idea or create a project to get started.": "Пока нет проектов. Создайте идею или проект, чтобы начать.",
  "Workspace settings": "Настройки пространства", "Channel workspace": "Пространство канала", "Selected channel": "Выбранный канал",
  "Choose…": "Выберите…", "YouTube connection": "Подключение YouTube", "Not connected": "Не подключён",
  "Create/select a local channel workspace and connect YouTube via OAuth.": "Создайте или выберите рабочее пространство канала и подключите YouTube.",
  "Create channel workspace": "Создать пространство канала", "Connect YouTube": "Подключить YouTube", "Disconnect YouTube": "Отключить YouTube",
  "Language": "Язык", "Timezone": "Часовой пояс", "Channel created.": "Канал создан.", "Channel creation failed": "Не удалось создать канал",
  "Video project": "Видеопроект", "Back to Projects": "К проектам", "Retry workflow": "Повторить процесс",
  "Cancel workflow": "Отменить процесс", "Publish to YouTube": "Опубликовать на YouTube", "Private": "Доступно только вам", "Unlisted": "Доступ по ссылке", "Public": "Открытый доступ",
  "English": "Английский", "Russian": "Русский", "Platform workspace": "Рабочее пространство платформы",
  "channels connected": "каналов подключено", "Unable to load channels": "Не удалось загрузить каналы",
  "Unable to start Google authorization": "Не удалось начать авторизацию Google", "Unable to create workspace": "Не удалось создать пространство",
  "Authentication failed": "Не удалось выполнить вход", "Google authentication failed": "Не удалось войти через Google",
  "Save": "Сохранить", "Cancel": "Отмена", "Delete": "Удалить", "Edit": "Изменить", "Search": "Поиск",
  "All": "Все", "Active": "Активно", "Completed": "Завершено", "Pending": "Ожидает", "Draft": "Черновик",
  "Status": "Статус", "Actions": "Действия", "Description": "Описание", "Created": "Создано", "Updated": "Обновлено",
  "Loading…": "Загрузка…", "Loading...": "Загрузка…", "Back": "Назад", "Next": "Далее", "Continue": "Продолжить",
  "No data available": "Нет данных", "No results found": "Ничего не найдено", "Refresh": "Обновить", "Generate": "Создать",
  "Title": "Название", "Type": "Тип", "Date": "Дата", "Name your project": "Назовите проект",
  "30-Day Content Factory": "Контент-план на 30 дней", "AI score": "Оценка ИИ", "Acknowledge": "Подтвердить", "Action": "Действие",
  "Action policies": "Политики действий", "Activate Autopilot": "Включить автопилот", "Active content pipeline": "Активный конвейер контента",
  "Active pipeline": "Активный конвейер", "After publication": "После публикации", "Agent": "Агент",
  "Agent Governance & Human Oversight": "Управление агентами и контроль человеком", "Agent Learning & Self-Improvement": "Обучение и саморазвитие агентов",
  "Agent Planner & Dynamic Workflow Graph": "Планировщик агентов и динамический граф процессов", "Agent activity": "Активность агентов",
  "Agent execution is persisted and can be inspected.": "История работы агентов сохраняется и доступна для просмотра.", "All events": "Все события",
  "Allocate budget across channels before production consumes it.": "Распределяйте бюджет между каналами до начала производства.",
  "Analytics → diagnosis → memory → next idea, while governance remains in control.": "Аналитика → выводы → память канала → новые идеи под контролем правил.",
  "Angle": "Угол подачи", "Approval queue": "Очередь согласования", "Approve": "Одобрить", "Authority": "Авторитетность",
  "Auto-generate ideas": "Автоматически создавать идеи", "Autonomous": "Автономный", "Autonomous Agent Runtime": "Среда выполнения агентов",
  "Autonomous Creative Director": "Автономный креативный директор", "Autonomous Execution": "Автономное выполнение",
  "Autonomous Research": "Автономное исследование", "Average video cost": "Средняя стоимость видео",
  "Balanced": "Сбалансированный", "Billing period": "Расчётный период", "Blueprints": "Творческие планы", "Brain version": "Версия аналитики канала",
  "Browse previous ideas, drafts, renders and publish states for this workspace.": "Просматривайте идеи, черновики, готовые видео и публикации этого пространства.",
  "Budget policy": "Бюджетная политика", "Build blueprint": "Создать план производства", "Build plan": "Составить план",
  "Build the next video.": "Подготовить следующее видео.", "Cadence (hours)": "Интервал (часы)", "Cancel at period end": "Отменить в конце периода",
  "Channel ID": "ID канала", "Channel growth": "Рост канала", "Channel overview": "Обзор канала", "Channels": "Каналы",
  "Checking provider runtime availability…": "Проверяем доступность провайдеров…", "Choose channel…": "Выберите канал…",
  "Compare consecutive research snapshots and surface observable changes in topic signals.": "Сравнивайте результаты исследований и отслеживайте изменения тем.",
  "Competition": "Конкуренция", "Confidence": "Уверенность", "Configured providers": "Настроенные провайдеры",
  "Content Factory": "Контент-фабрика", "Content decision engine v2.0": "Система выбора контента 2.0", "Content factory": "Контент-фабрика",
  "Content intelligence": "Аналитика контента", "Control plane": "Центр управления", "Cost": "Стоимость", "Cost-aware orchestration": "Управление с учётом стоимости",
  "Create a new immutable revision without touching the published source.": "Создайте новую версию, не изменяя опубликованный оригинал.",
  "Create from idea": "Создать из идеи", "Create improved version": "Создать улучшенную версию", "Create project": "Создать проект",
  "Create research schedule": "Создать расписание исследований", "Create strategy proposal": "Создать предложение стратегии", "Create targeted re-edit": "Создать точечный монтаж",
  "Creator Autopilot": "Автопилот автора", "Creative direction": "Креативное направление", "Creative score": "Оценка креатива",
  "Current": "Текущий", "Current + forecast production": "Текущее и прогнозируемое производство", "Current password": "Текущий пароль",
  "Current usage": "Текущее использование", "Daily spend": "Расходы за день", "Delta": "Изменение", "Demand": "Спрос",
  "Deterministic media validation before publication.": "Проверка медиафайлов перед публикацией.", "Dimension": "Показатель", "Director plans": "Планы режиссёра",
  "Discover public signals, persistent research entities, and opportunity hypotheses for this channel.": "Изучайте открытые сигналы, результаты исследований и новые возможности для канала.",
  "Download personal-data export": "Скачать архив личных данных", "Duration": "Длительность", "Emergency kill switch": "Аварийная остановка",
  "Every scan is recorded with results, opportunities, generated ideas and error state.": "Каждое исследование сохраняет результаты, возможности, идеи и сведения об ошибках.",
  "Every video is an auditable AI workflow with agent history and media artifacts.": "Для каждого видео сохраняется проверяемая история работы ИИ и созданные материалы.",
  "Experiment": "Эксперимент", "Export my data": "Экспортировать мои данные", "Export personal data, review privacy requests, and request account erasure.": "Экспортируйте данные, проверяйте запросы конфиденциальности и удаляйте аккаунт.",
  "Fallback decisions": "Решения о резервных провайдерах", "For local development, configure your Google OAuth client secret in": "Для локальной разработки настройте секрет клиента Google OAuth в файле",
  "Forecast": "Прогноз", "Freshness (days)": "Актуальность (дни)", "Freshness window (days)": "Период актуальности (дни)",
  "Gap": "Разрыв", "Generate a publishing calendar, turn slots into projects, and let the worker start production before each deadline.": "Создайте календарь публикаций, превратите слоты в проекты и запускайте производство заранее.",
  "Goal decomposition, capability matching, budget-aware planning, governance admission and replanning.": "Разбивка целей, подбор возможностей, планирование бюджета и проверка правил.",
  "Heuristic signals from the latest research scan; not performance guarantees.": "Оценочные сигналы последнего исследования, а не гарантия результата.", "Hook": "Зацепка", "Hypothesis": "Гипотеза",
  "Ideas are generated and ranked against the current channel memory.": "Идеи создаются и ранжируются с учётом данных канала.", "Ideas waiting for a blueprint": "Идеи, ожидающие плана производства",
  "Learning loop": "Цикл обучения", "Limit": "Лимит", "Live backend data": "Актуальные данные сервера", "Load lineage": "Загрузить историю версий",
  "Manual approval": "Подтверждать вручную", "Materialize all": "Создать все проекты", "Materialize ready": "Создать готовые проекты", "Max runs / day": "Максимум запусков в день",
  "Media stack": "Медиаинструменты", "Memory": "Память", "Metric": "Показатель", "Monthly budget": "Месячный бюджет", "Monthly price": "Цена за месяц", "Monthly spend": "Расходы за месяц",
  "Multimodal Intelligence": "Мультимодальная аналитика", "New": "Новый", "No agent runs yet.": "Агенты ещё не запускались.",
  "No allocations yet. Run a rebalance.": "Распределений пока нет. Запустите перебалансировку.", "No blueprints yet.": "Планов производства пока нет.", "No candidates": "Нет вариантов",
  "No channels linked yet.": "Каналы ещё не подключены.", "No custom profiles. Built-in defaults are selected from environment settings.": "Пользовательских профилей нет. Используются настройки окружения.",
  "No custom provider profiles. The built-in provider catalog will be used.": "Используются встроенные профили провайдеров.", "No decisions yet.": "Решений пока нет.", "No execution runs yet.": "Запусков ещё не было.",
  "No experiments yet. Create one from an optimization report through the API.": "Экспериментов пока нет. Создайте эксперимент из отчёта оптимизации.", "No governance events yet.": "Событий контроля пока нет.", "No ideas yet. Generate the first batch.": "Идей пока нет. Создайте первую подборку.",
  "No multimodal graphs yet. Create a video project and run its workflow.": "Мультимодальных графов пока нет. Создайте видеопроект и запустите процесс.", "No open performance alerts.": "Нет активных предупреждений об эффективности.",
  "No optimization decisions yet.": "Решений об оптимизации пока нет.", "No pending approvals.": "Нет ожидающих согласования запросов.", "No plans yet.": "Планов пока нет.",
  "No post-publish monitors yet.": "Нет наблюдений после публикации.", "No privacy requests loaded.": "Запросы конфиденциальности не загружены.", "No project found.": "Проект не найден.",
  "No projects for the selected channel.": "Для выбранного канала проектов пока нет.", "No provider budgets configured.": "Бюджеты провайдеров не настроены.",
  "No quality reports yet. Run a workflow or a manual quality check.": "Отчётов о качестве пока нет. Запустите процесс или проверку вручную.",
  "No recurring research schedules yet.": "Повторяющиеся исследования ещё не запланированы.", "No routing decisions yet. Start a workflow to populate the audit trail.": "Решений маршрутизации пока нет. Запустите процесс, чтобы создать журнал.",
  "No runs recorded yet.": "Запусков пока нет.", "No version data loaded.": "Данные о версиях не загружены.", "OAuth credentials stay on the backend; the browser never receives refresh tokens.": "Данные OAuth хранятся на сервере; браузер не получает токены обновления.",
  "One control plane for multiple channels, providers and production costs.": "Единый центр управления каналами, провайдерами и затратами на производство.", "Open Autonomous Execution": "Открыть автономное выполнение", "Open Content Factory": "Открыть контент-фабрику",
  "Open alerts": "Открыть предупреждения", "Open analytics": "Открыть аналитику", "Open brain": "Открыть аналитику канала", "Open routing": "Открыть маршрутизацию",
  "Opportunity signals": "Сигналы возможностей", "Optimization decisions become actions only after permission, Quality Gate and budget checks.": "Решения об оптимизации выполняются после проверки разрешений, качества и бюджета.",
  "Optimization lab": "Лаборатория оптимизации", "Pending human decisions": "Решения, ожидающие человека", "Performance signals → evidence → bounded next action.": "Сигналы эффективности → данные → контролируемое действие.",
  "Persistent memory built from published-video performance.": "Долговременная память на основе эффективности опубликованных видео.", "Plan generator": "Генератор планов", "Plans, entitlements, usage and billing-provider state.": "Планы, доступные функции, использование и состояние оплаты.",
  "Privacy & security": "Конфиденциальность и безопасность", "Production graph": "Граф производства", "Production memory": "Память о производстве", "Production quality": "Качество производства",
  "Provider health is unavailable or disabled.": "Состояние провайдера недоступно или отключено.", "Provider readiness": "Готовность провайдеров", "Provider router": "Маршрутизатор провайдеров",
  "Provider routing": "Маршрутизация провайдеров", "Research Graph": "Граф исследований", "Research intelligence v1.9": "Аналитика исследований 1.9",
  "Research scheduler v1.8": "Планировщик исследований 1.8", "Risk tiers, approval queues, automation policies, emergency stop and the decision journal.": "Уровни риска, согласования, политики автоматизации, аварийная остановка и журнал решений.",
  "Run Creative Intelligence first.": "Сначала запустите креативную аналитику.", "Run Opportunity Intelligence after research data is available.": "Запустите анализ возможностей после получения результатов исследований.",
  "Run Research or wait for the scheduler to create snapshots.": "Запустите исследование или дождитесь планировщика.", "Run a research scan to populate the opportunity layer.": "Запустите исследование, чтобы найти новые возможности.",
  "Runtime checks show which providers can be used now. Secret values are never displayed.": "Проверка показывает доступных провайдеров. Секретные значения не отображаются.",
  "See which video, image and voice providers are available for the next production.": "Посмотрите, какие провайдеры видео, изображений и голоса доступны для производства.",
  "Select a plan to inspect the schedule.": "Выберите план, чтобы посмотреть расписание.", "Select a project": "Выберите проект", "Select a schedule to inspect its run history.": "Выберите расписание, чтобы посмотреть историю запусков.",
  "Stored decisions remain reusable by Autopilot and production agents.": "Сохранённые решения доступны автопилоту и производственным агентам.", "Sync YouTube Analytics into the Channel Brain database.": "Загрузите аналитику YouTube в базу данных канала.",
  "Task queue": "Очередь задач", "The export excludes password hashes, session tokens, raw API keys, and encrypted provider credentials.": "В архив не входят хеши паролей, токены сессий, ключи API и зашифрованные данные провайдеров.",
  "The first scan runs immediately unless you set a future timestamp in the API.": "Первое исследование запускается сразу, если в API не задано будущее время.", "The renderer has not produced a video yet.": "Видео ещё не создано.",
  "The system chooses format, hook, duration, visual pacing and an experiment for each concept.": "Система подбирает формат, зацепку, длительность, темп и эксперимент для каждой идеи.",
  "The workflow is executed asynchronously; this page polls for progress.": "Процесс выполняется в фоне; страница периодически обновляет статус.", "Thumbnail will appear after production.": "Обложка появится после производства.",
  "Track observational tests for titles, thumbnails, hooks, pacing and topic angles.": "Отслеживайте тесты заголовков, обложек, зацепок, темпа и подачи тем.",
  "Turn a concept into a production strategy before rendering starts.": "Подготовьте стратегию производства до начала рендеринга.", "Turn a research-backed idea into a governed production workflow.": "Превратите подтверждённую исследованием идею в управляемый процесс производства.",
  "Turn research opportunities and recent trend events into auditable content priorities.": "Преобразуйте результаты исследований и новые тренды в проверяемые приоритеты контента.",
  "Turn scene evidence into bounded, explainable edit actions without rewriting the source video.": "Используйте данные о сценах для понятных точечных правок без изменения исходного видео.",
  "Versioned re-edit": "Версионный повторный монтаж", "Video Understanding": "Анализ видео", "Video preview": "Предпросмотр видео", "Video projects:": "Видеопроекты:",
  "Watch retention, views and CTR signals after a video is published.": "Отслеживайте удержание аудитории, просмотры и CTR после публикации видео.",
  "Why AI was allowed to act": "Почему ИИ разрешили выполнить действие", "Worker-driven": "Управляется рабочим процессом", "Workspace billing": "Оплата пространства",
  "Yes": "Да", "YouTube Data API": "YouTube Data API", "Trend boost": "Рост тренда", "Trend events": "События трендов",
  "Heuristic prioritization — signals are evidence for planning, not guaranteed outcomes.": "Приоритеты рассчитываются эвристически: сигналы помогают планированию, но не гарантируют результат.",
  "CTR": "CTR", "HTTP JSON": "HTTP JSON", "G": "G",
  "Open Autopilot": "Открыть автопилот", "Connect channel": "Подключить канал", "No active project": "Нет активного проекта",
  "Your current project is moving through the production graph.": "Текущий проект проходит этапы производственного графа.",
  "Start a project to activate the pipeline.": "Создайте проект, чтобы запустить конвейер.", "Net subscribers from the analytics layer for this selected channel.": "Чистый прирост подписчиков выбранного канала.",
};

const autoRu: Array<[RegExp, string]> = [
  [/Failed to load/gi, "Не удалось загрузить"], [/Unable to load/gi, "Не удалось загрузить"],
  [/Unable to create/gi, "Не удалось создать"], [/Could not create/gi, "Не удалось создать"],
  [/Failed to create/gi, "Не удалось создать"], [/Failed to refresh/gi, "Не удалось обновить"],
  [/Generation failed/gi, "Ошибка генерации"], [/Plan generation failed/gi, "Ошибка генерации плана"],
  [/Activation failed/gi, "Ошибка активации"], [/Pause failed/gi, "Ошибка приостановки"],
  [/Materialization failed/gi, "Ошибка материализации"], [/Cancellation failed/gi, "Ошибка отмены"],
  [/OAuth start failed/gi, "Ошибка запуска OAuth"], [/Export failed/gi, "Ошибка экспорта"],
  [/Deletion request failed/gi, "Ошибка запроса удаления"], [/Workflow failed/gi, "Ошибка рабочего процесса"],
  [/Retry failed/gi, "Ошибка повторного запуска"], [/Research failed/gi, "Ошибка исследования"],
  [/Idea generation failed/gi, "Ошибка генерации идей"], [/Scheduler action failed/gi, "Ошибка действия планировщика"],
  [/Create a channel in Settings first/gi, "Сначала создайте канал в настройках"], [/Create a channel first/gi, "Сначала создайте канал"],
  [/Select a channel first/gi, "Сначала выберите канал"], [/Enter a project ID/gi, "Введите ID проекта"],
  [/No active project/gi, "Нет активного проекта"], [/No projects yet/gi, "Проектов пока нет"],
  [/No ideas yet/gi, "Идей пока нет"], [/No candidates/gi, "Кандидатов нет"], [/No channels linked yet/gi, "Каналы пока не подключены"],
  [/No pending approvals/gi, "Ожидающих согласований нет"], [/No decisions yet/gi, "Решений пока нет"],
  [/No execution runs yet/gi, "Запусков выполнения пока нет"], [/No experiments yet/gi, "Экспериментов пока нет"],
  [/Generate 10 ideas/gi, "Сгенерировать 10 идей"], [/Generate content plan/gi, "Сгенерировать контент-план"],
  [/Create project/gi, "Создать проект"], [/Create schedule/gi, "Создать расписание"], [/Build plan/gi, "Создать план"],
  [/Analyze video/gi, "Проанализировать видео"], [/Scan opportunity/gi, "Сканировать возможности"],
  [/Open project/gi, "Открыть проект"], [/Open analytics/gi, "Открыть аналитику"], [/Open routing/gi, "Открыть маршрутизацию"],
  [/Open Autopilot/gi, "Открыть автопилот"], [/Connect channel/gi, "Подключить канал"], [/Choose plan/gi, "Выбрать тариф"],
  [/Enable/gi, "Включить"], [/Disable/gi, "Отключить"], [/Pause/gi, "Приостановить"], [/Approve/gi, "Одобрить"], [/Reject/gi, "Отклонить"],
  [/Delete/gi, "Удалить"], [/Cancel/gi, "Отмена"], [/Save/gi, "Сохранить"], [/Search/gi, "Поиск"], [/Refresh/gi, "Обновить"],
  [/Loading\.\.\./gi, "Загрузка…"], [/Loading/gi, "Загрузка"], [/Ready/gi, "Готово"], [/Unavailable/gi, "Недоступно"],
  [/Enabled/gi, "Включено"], [/Disabled/gi, "Отключено"], [/Current/gi, "Текущий"], [/New/gi, "Новый"],
  [/Pattern/gi, "Паттерн"], [/Confidence/gi, "Уверенность"], [/Competition/gi, "Конкуренция"], [/Demand/gi, "Спрос"],
  [/Duration/gi, "Длительность"], [/Forecast/gi, "Прогноз"], [/Hypothesis/gi, "Гипотеза"], [/Metric/gi, "Метрика"],
  [/Cost/gi, "Стоимость"], [/Status/gi, "Статус"], [/Actions/gi, "Действия"], [/Description/gi, "Описание"],
  [/Created/gi, "Создано"], [/Updated/gi, "Обновлено"], [/Date/gi, "Дата"], [/Title/gi, "Название"], [/Type/gi, "Тип"],
  [/Views/gi, "Просмотры"], [/Subscribers/gi, "Подписчики"], [/Watch time/gi, "Время просмотра"], [/Projects/gi, "Проекты"],
  [/Channel UUID/gi, "UUID канала"], [/Channel ID/gi, "ID канала"], [/Research signal/gi, "Сигнал исследования"],
  [/Daily Opportunity Scan/gi, "Ежедневное сканирование возможностей"], [/AI agents/gi, "ИИ-агенты"],
  [/Live backend data/gi, "Данные в реальном времени"], [/Not configured/gi, "Не настроено"]
];

function autoTranslateRu(text: string): string {
  if (!text || !/[A-Za-z]/.test(text)) return text;
  let result = text;
  for (const [pattern, replacement] of autoRu) result = result.replace(pattern, replacement);
  return result;
}

type LocaleContextValue = { language: Language; setLanguage: (language: Language) => void; t: (text: string) => string };
const LocaleContext = createContext<LocaleContextValue>({ language: "ru", setLanguage: () => undefined, t: text => ru[text] || autoTranslateRu(text) });

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("ru");
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "ru" || stored === "en") setLanguageState(stored);
  }, []);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  function setLanguage(next: Language) {
    window.localStorage.setItem(STORAGE_KEY, next);
    setLanguageState(next);
  }
  const t = (text: string) => language === "ru" ? ru[text] || autoTranslateRu(text) : text;
  return <LocaleContext.Provider value={{ language, setLanguage, t }}>{children}</LocaleContext.Provider>;
}

export function useLocale() { return useContext(LocaleContext); }

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { language, setLanguage } = useLocale();
  return <div className={`languageSwitcher ${className}`} role="group" aria-label={language === "ru" ? "Язык интерфейса" : "Interface language"}>
    <button type="button" aria-pressed={language === "ru"} onClick={() => setLanguage("ru")}>RU</button>
    <span aria-hidden="true">·</span>
    <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
  </div>;
}

function localizeNode(node: ReactNode, t: (text: string) => string): ReactNode {
  if (typeof node === "string") {
    const leading = node.match(/^\s*/)?.[0] || "";
    const trailing = node.match(/\s*$/)?.[0] || "";
    const core = node.trim();
    return core ? `${leading}${t(core)}${trailing}` : node;
  }
  if (Array.isArray(node)) return node.map((child, index) => <Fragment key={index}>{localizeNode(child, t)}</Fragment>);
  if (!isValidElement(node)) return node;
  const element = node as ReactElement<Record<string, unknown>>;
  const props = { ...element.props };
  if ("children" in props) props.children = localizeNode(props.children as ReactNode, t);
  for (const attr of ["title", "placeholder", "aria-label", "aria-description", "alt"]) {
    if (typeof props[attr] === "string") props[attr] = t(props[attr] as string);
  }
  return cloneElement(element, props);
}

export function LocalizedContent({ children }: { children: ReactNode }) {
  const { t } = useLocale();
  return <>{localizeNode(children, t)}</>;
}
