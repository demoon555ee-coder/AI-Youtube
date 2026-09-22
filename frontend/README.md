# YouTube AI Platform Web v2.8

Live SaaS frontend for the cumulative YouTube AI Platform backend.

Set `NEXT_PUBLIC_API_BASE` to the FastAPI URL, then run:

```bash
npm install
npm run dev
```

Routes:

- `/` Dashboard
- `/ideas` Content Factory
- `/projects` Project list
- `/projects/:id` Live workflow + video preview + publish
- `/brain` Channel Brain
- `/analytics` YouTube Analytics sync
- `/settings` Channel + YouTube OAuth

- `/portfolio` Portfolio Brain and provider budget overview
- `/routing` Provider routing and fallback audit


## v1.8 Research Scheduler

The web app includes `/research-scheduler` for recurring scans, manual runs, pause/enable controls, and run history.
