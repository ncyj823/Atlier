const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API_KEY = process.env.EXPO_PUBLIC_API_KEY || "";

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = new Headers(opts.headers || {});
  headers.set("Content-Type", "application/json");

  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

export type Client = {
  id: string;
  name: string;
  whatsapp: string;
  email: string;
  measurements: Record<string, string>;
  notes: string;
  created_at: string;
};

export type EventItem = {
  id: string;
  title: string;
  mode: string;
  start_iso: string;
  duration_minutes: number;
  client_id?: string | null;
  client_name?: string;
  client_email?: string;
  notes: string;
  meet_link: string;
  reminders: string[];
  created_at: string;
};

export type InvoiceItem = {
  id: string;
  description: string;
  amount: number;
  status: "pending" | "cleared";
  created_at: string;
};

export type PdfMeta = { id: string; name: string; uploaded_at: string; size_bytes: number };

export type Project = {
  id: string;
  uid?: string;
  client_id: string;
  client_name?: string;
  title: string;
  delivery_location: string;
  deadline: string | null;
  description: string;
  total_amount: number;
  paid_amount: number;
  status: "ongoing" | "completed";
  created_at: string;
  updated_at: string;
};

export type CanvasStroke = { d: string; color: string; width: number };
export type Canvas = { project_id: string; gender: "female" | "male"; strokes: CanvasStroke[]; updated_at: string };

export const api = {
  seed: () => req<{ ok: boolean }>("/api/_seed", { method: "POST" }),
  listClients: () => req<Client[]>("/api/clients"),
  getClient: (id: string) =>
    req<{ client: Client; pdfs: PdfMeta[]; invoice: { items: InvoiceItem[] } }>(`/api/clients/${id}`),
  createClient: (body: Partial<Client>) =>
    req<Client>("/api/clients", { method: "POST", body: JSON.stringify(body) }),
  updateClient: (id: string, body: Partial<Client>) =>
    req<Client>(`/api/clients/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteClient: (id: string) => req<{ ok: boolean }>(`/api/clients/${id}`, { method: "DELETE" }),

  uploadPdf: (clientId: string, name: string, dataBase64: string) =>
    req<PdfMeta>(`/api/clients/${clientId}/pdfs`, {
      method: "POST",
      body: JSON.stringify({ name, data_base64: dataBase64 }),
    }),
  deletePdf: (clientId: string, pdfId: string) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/pdfs/${pdfId}`, { method: "DELETE" }),

  addInvoiceItem: (clientId: string, body: Partial<InvoiceItem>) =>
    req<InvoiceItem>(`/api/clients/${clientId}/invoices/items`, { method: "POST", body: JSON.stringify(body) }),
  updateInvoiceItem: (clientId: string, itemId: string, body: Partial<InvoiceItem>) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/invoices/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteInvoiceItem: (clientId: string, itemId: string) =>
    req<{ ok: boolean }>(`/api/clients/${clientId}/invoices/items/${itemId}`, { method: "DELETE" }),

  share: (clientId: string) => req<{ token: string; url: string }>(`/api/clients/${clientId}/share`, { method: "POST" }),

  parse: (text: string) =>
    req<{
      title: string;
      mode: string;
      client_name: string | null;
      start_iso: string;
      duration_minutes: number;
      timezone: string;
      notes: string;
      client_id: string | null;
      client_email: string;
    }>("/api/schedule/parse", { method: "POST", body: JSON.stringify({ text }) }),

  createEvent: (body: Partial<EventItem>) =>
    req<EventItem>("/api/events", { method: "POST", body: JSON.stringify(body) }),
  listEvents: (fromIso?: string, toIso?: string) => {
    const q = fromIso && toIso ? `?from_iso=${encodeURIComponent(fromIso)}&to_iso=${encodeURIComponent(toIso)}` : "";
    return req<EventItem[]>(`/api/events${q}`);
  },
  deleteEvent: (id: string) => req<{ ok: boolean }>(`/api/events/${id}`, { method: "DELETE" }),
  rescheduleEvent: (id: string, startIso: string) =>
    req<EventItem>(`/api/events/${id}`, { method: "PUT", body: JSON.stringify({ start_iso: startIso }) }),

  // Projects
  listProjects: () => req<Project[]>("/api/projects"),
  getProject: (id: string) =>
    req<{ project: Project; client: Client; pdfs: PdfMeta[]; canvas: Canvas }>(`/api/projects/${id}`),
  createProject: (body: Partial<Project> & { client_id: string; title: string; mannequin_gender?: "female" | "male" }) =>
    req<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (id: string, body: Partial<Project>) =>
    req<Project>(`/api/projects/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteProject: (id: string) =>
    req<{ ok: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),

  uploadProjectPdf: (projectId: string, name: string, dataBase64: string) =>
    req<PdfMeta>(`/api/projects/${projectId}/pdfs`, {
      method: "POST", body: JSON.stringify({ name, data_base64: dataBase64 }),
    }),
  deleteProjectPdf: (projectId: string, pdfId: string) =>
    req<{ ok: boolean }>(`/api/projects/${projectId}/pdfs/${pdfId}`, { method: "DELETE" }),

  getCanvas: (projectId: string) => req<Canvas>(`/api/projects/${projectId}/canvas`),
  saveCanvas: (projectId: string, body: { gender: "female" | "male"; strokes: CanvasStroke[] }) =>
    req<{ ok: boolean }>(`/api/projects/${projectId}/canvas`, { method: "PUT", body: JSON.stringify(body) }),

  clientProjects: (clientId: string) => req<Project[]>(`/api/clients/${clientId}/projects`),
};
