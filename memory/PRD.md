# Atelier — Fashion Freelancer Business Management App

## Product
Personal business management tool for a fashion/design freelancer. Single-user (no auth). Editorial mobile app built with Expo Router (SDK 54) + FastAPI + MongoDB.

## Core Features
1. **Smart Scheduling (NL → Event)** — Type "Schedule a design call for Anaïs at 6pm IST on coming Wednesday". Claude Sonnet 4.5 (via Emergent Universal LLM key) parses into structured event (title, mode, client, datetime, tz). Backend auto-generates a mock Google Meet link, computes 3 reminders (1d / 1h / 15m before), and emails the client.
2. **Client Profile Manager** — Create clients with name, email, WhatsApp, notes and measurements (Bust/Waist/Hip/Shoulder). Per-client: PDF design sheets uploads (base64) sorted by date, invoice table with pending/cleared status. Updating an invoice item auto-emails the client. Each profile gets a shareable read-only HTML URL.
3. **Color-Coded Calendar** — Month grid with toggleable mode chips: Design Call (Terracotta), Measurement Call (Ochre), Sending Pieces (Sage), Personal (Warm Grey). Day cells show colored dots, tap to view that day's events.

## Tech Stack
- **Frontend**: Expo Router (SDK 54), React Native, expo-document-picker, expo-file-system, react-native-safe-area-context, @expo/vector-icons (Feather), expo-haptics.
- **Backend**: FastAPI, Motor (MongoDB), emergentintegrations + Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`), Resend for emails (MOCKED — logs to console when `RESEND_API_KEY` is empty), dateutil/pytz for timezones.
- **Storage**: MongoDB collections — clients, events, pdfs (base64), invoices, share_tokens.

## Integrations
- **Claude Sonnet 4.5** via Emergent Universal LLM Key (already configured in backend `.env`).
- **Resend** — env `RESEND_API_KEY` left blank → emails are MOCKED (logged). User can add real key later.
- **Google Meet / Calendar / Gmail** — MOCKED (generates Meet-style links, no real Calendar API call). User opted to add real OAuth in a follow-up iteration.

## Endpoints (prefix `/api`)
- `POST /schedule/parse` `POST /events` `GET /events` `DELETE /events/{id}`
- `GET/POST/PUT/DELETE /clients[/{id}]`
- `POST/DELETE /clients/{id}/pdfs[/{pdf_id}]` `GET /clients/{id}/pdfs/{pdf_id}`
- `POST/PUT/DELETE /clients/{id}/invoices/items[/{item_id}]`
- `POST /clients/{id}/share` → returns `{token, url}`; `GET /share/{token}` returns public HTML page
- `POST /_seed` — seeds 3 demo clients

## Open Items / Follow-ups
- Real Google OAuth (Calendar + Gmail + Meet) — pending user credentials.
- Real email sending via Resend — pending API key.

## Data Model (current)
- **clients** — name, email, whatsapp, measurements, notes (used as a contact directory).
- **projects** — client_id, title, delivery_location, deadline (YYYY-MM-DD), description, total_amount, paid_amount, status (ongoing|completed), created_at, updated_at. Sorted by deadline asc; no-deadline last.
- **pdfs** — now linked to `project_id` (design sheets per project).
- **canvases** — one per project, `{ project_id, gender, strokes[{d,color,width}], updated_at }`. Auto-created when a project is created.
- **events** — unchanged (calendar + reminders).
- **invoices** — legacy collection from earlier iteration, no longer in the UI but endpoints remain.

## UI structure
- Tab 1 Today (NL Send + heavy-day overload + reschedule sheet)
- Tab 2 Calendar (month, mode toggles, bigger cells, scrollable)
- Tab 3 Projects (sorted by deadline, payment progress, status pills)
- /project/[id] — payment progress bar, dates, tappable client-link, PDF upload, MannequinCanvas (SVG silhouette + freehand strokes, female/male toggle, color & width palette, undo/clear/save)
- /client/[id] — client info, total/ongoing/completed counts, list of all projects (tappable)
