# Atelier — Fashion Freelancer Business Management App

## Product
Personal business management tool for a fashion/design freelancer. Single-user (no auth). Editorial mobile app built with Expo Router (SDK 54) + FastAPI + MongoDB. Iteration 4 added Google Calendar/Meet real integration, sequential project UIDs, auto-deadline reminders, email reminders, and an image-based mannequin canvas.

## Tabs
1. **Today** — NL Send composer (Claude Sonnet 4.5), voice (Whisper), heavy-day red banner, per-event Reschedule.
2. **Calendar** — month grid, mode toggles, bar markers, sticky header.
3. **Projects** — sorted by deadline asc. Card: **client name LARGE serif**, project title small italic, **ATL-NNNN** UID badge, payment progress bar, ongoing/completed pill.

## Routes
- `/project/[id]` — payment progress, dates, tappable client link, PDFs, **Mannequin Canvas** (uploaded female + male croquis, single black ink, round caps, Undo + Save).
- `/client/[id]` — client info, project stats, tappable project list.

## Integrations
- **Claude Sonnet 4.5** (Emergent LLM key) — NL parsing of scheduling commands.
- **OpenAI Whisper-1** (Emergent LLM key) — voice → text.
- **Gmail SMTP** (`nikhil.dg2003@gmail.com` + app password) — meeting invites, reschedules, invoice updates, scheduled reminders.
- **Google Calendar API + Meet** — creates real events with `conferenceData.createRequest` for real Meet links; adds client + me as attendees so Google auto-emails them. ⚠ Refresh token currently returns `unauthorized_client` — user is regenerating via OAuth Playground with correct client. System gracefully falls back to mock meet links until fixed.
- **APScheduler** (in-memory) — schedules 3 reminder emails per event: **morning-of (9 AM local), 30 min before, on schedule**. Emails go to client + GMAIL_USER.

## Auto behaviors
- Each project gets sequential `uid` `ATL-NNNN` via counter doc.
- When a project is created or its deadline changes, an event with `mode="sending_pieces"` is auto-created/updated 2 days before the deadline (idempotent — never duplicates).
- Event create/reschedule/delete syncs to Google Calendar (+ Meet) when configured.

## Data Model
- clients, projects (with uid + counter), events (with auto_kind, project_id, google_event_id), pdfs (project_id), canvases (project_id, gender, strokes), share_tokens, invoices (legacy).

## Open Items
- ⏳ **Supabase migration** — creds in `.env`, full Mongo → Postgres + Supabase Storage rewrite deferred to next session.
- ⏳ **Google OAuth refresh token** — user regenerating with correct client.
- APScheduler uses MemoryJobStore — reminders are lost on backend restart. After Supabase migration, switch to a persistent jobstore.
