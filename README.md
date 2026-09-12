# Mira: white-label theme + URL fetch package

## 1. MIGRATION — supabase/migrations/0002_white_label_theme.sql
```sql
alter table public.businesses
  add column if not exists theme jsonb not null default '{"primary":"#0f766e","secondary":"#115e59","surface":"#ffffff","text":"#0f172a","radius":16,"font":"system","logo_url":null,"show_powered_by":false}'::jsonb;
```

## 2. TYPES — add to lib/types.ts
```ts
export type MiraTheme = {
  primary: string;
  secondary: string;
  surface: string;
  text: string;
  radius: number;
  font: "system" | "serif" | "mono";
  logo_url: string | null;
  show_powered_by: boolean;
};

export const defaultTheme: MiraTheme = {
  primary: "#0f766e", secondary: "#115e59", surface: "#ffffff",
  text: "#0f172a", radius: 16, font: "system", logo_url: null, show_powered_by: false,
};

export function normalizeTheme(raw: unknown): MiraTheme {
  const t = (raw ?? {}) as Partial<MiraTheme>;
  return {
    primary: typeof t.primary === "string" ? t.primary : defaultTheme.primary,
    secondary: typeof t.secondary === "string" ? t.secondary : defaultTheme.secondary,
    surface: typeof t.surface === "string" ? t.surface : defaultTheme.surface,
    text: typeof t.text === "string" ? t.text : defaultTheme.text,
    radius: typeof t.radius === "number" ? t.radius : defaultTheme.radius,
    font: t.font === "serif" || t.font === "mono" ? t.font : "system",
    logo_url: typeof t.logo_url === "string" ? t.logo_url : null,
    show_powered_by: t.show_powered_by === true,
  };
}
```

## 3. buildContext — in lib/ai/buildContext.ts
```ts
// in the select:
.select("id,name,currency,timezone,ai_tone,ai_instructions,hours_note,social_links,theme")

// in the returned context:
theme: normalizeTheme(business?.theme),
```

## 4. SAVE API — app/api/admin/businesses/[businessId]/theme/route.ts
```ts
import { NextResponse } from "next/server";
import { createRouteHandlerClient } from "@supabase/auth-helpers-nextjs";
import { cookies } from "next/headers";
import { normalizeTheme } from "@/lib/types";

export async function PUT(_req: Request, { params }: { params: { businessId: string } }) {
  const supabase = createRouteHandlerClient({ cookies });
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const theme = normalizeTheme(await _req.json());
  const { data: biz } = await supabase.from("businesses").select("owner_id").eq("id", params.businessId).single();
  if (!biz || biz.owner_id !== user.id) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const { error } = await supabase.from("businesses").update({ theme }).eq("id", params.businessId);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, theme });
}
```

## 5. THEME FORM — app/admin/(protected)/businesses/[businessId]/settings/ThemeForm.tsx
```tsx
"use client";
import { useState } from "react";
import { createClient } from "@/lib/supabase/browser";
import type { MiraTheme } from "@/lib/types";
import { defaultTheme } from "@/lib/types";

const FONTS = ["system", "serif", "mono"] as const;
const SWATCHES = ["primary", "secondary", "surface", "text"] as const;

export function ThemeForm({ businessId, initial }: { businessId: string; initial?: Partial<MiraTheme> }) {
  const [theme, setTheme] = useState<MiraTheme>({ ...defaultTheme, ...initial });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const set = <K extends keyof MiraTheme>(key: K, v: MiraTheme[K]) => setTheme((t) => ({ ...t, [key]: v }));

  async function uploadLogo(file: File) {
    const supabase = createClient();
    const path = `${businessId}/logo-${Date.now()}`;
    const { error } = await supabase.storage.from("business-assets").upload(path, file, { upsert: true });
    if (error) return setMsg("logo upload failed: " + error.message);
    const { data } = supabase.storage.from("business-assets").getPublicUrl(path);
    set("logo_url", data.publicUrl);
  }

  async function save() {
    setSaving(true); setMsg("");
    const res = await fetch(`/api/admin/businesses/${businessId}/theme`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(theme),
    });
    setSaving(false);
    setMsg(res.ok ? "theme saved" : "save failed");
  }

  return (
    <div className="space-y-6 rounded-2xl glass-panel p-6">
      <h3>White-label theme</h3>
      <div className="flex flex-wrap items-center gap-5">
        {SWATCHES.map((k) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            {k}
            <input type="color" value={theme[k] as string} onChange={(e) => set(k, e.target.value as never)} />
          </label>
        ))}
      </div>
      <label className="block text-sm">
        Corner radius: {theme.radius}px
        <input type="range" min={0} max={32} value={theme.radius} onChange={(e) => set("radius", Number(e.target.value))} className="w-full" />
      </label>
      <label className="block text-sm">
        Font
        <select value={theme.font} onChange={(e) => set("font", e.target.value as MiraTheme["font"])} className="ml-2">
          {FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>
      <div className="flex items-center gap-3">
        {theme.logo_url && <img src={theme.logo_url} alt="logo" className="h-10 w-10 rounded-lg object-cover" />}
        <input type="file" accept="image/*" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={theme.show_powered_by} onChange={(e) => set("show_powered_by", e.target.checked)} />
        Show "Powered by Mira"
      </label>
      <div className="flex items-center gap-4">
        <button onClick={save} disabled={saving} className="rounded-xl px-4 py-2 text-white" style={{ background: theme.primary }}>
          {saving ? "saving..." : "Save theme"}
        </button>
        {msg && <span className="text-sm">{msg}</span>}
      </div>
    </div>
  );
}
```

## 6. WIDGET — app/chat/[businessSlug]/ChatWindow.tsx
```tsx
const theme = normalizeTheme(business?.theme);
const rootStyle = {
  "--mira-primary": theme.primary,
  "--mira-secondary": theme.secondary,
  "--mira-surface": theme.surface,
  "--mira-text": theme.text,
  "--mira-radius": `${theme.radius}px`,
  fontFamily: theme.font === "serif" ? "Georgia, serif" : theme.font === "mono" ? "ui-monospace, monospace" : "system-ui, sans-serif",
} as React.CSSProperties;

// root container:
<div style={rootStyle} className="mira-widget">

// header (replaces bg-accent):
<div className="mira-header" style={{ background: "var(--mira-primary)" }}>
  {theme.logo_url ? <img src={theme.logo_url} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span>{name[0]}</span>}
</div>

// powered-by line — wrap in a condition:
{theme.show_powered_by && <a className="mira-powered-by">Powered by Mira AI</a>}
```

```css
.mira-widget { background: var(--mira-surface); color: var(--mira-text); border-radius: var(--mira-radius); }
.mira-bubble, .mira-header, .mira-user-msg { background: var(--mira-primary); color: var(--mira-surface); }
.mira-ai-msg { background: var(--mira-secondary); color: var(--mira-surface); }
.mira-powered-by { color: var(--mira-text); opacity: .6; font-size: 11px; }
```

## 7. EMBED OVERRIDES — in public/embed.js
```js
const overrides = {};
if (el.dataset.title) overrides.headerTitle = el.dataset.title;
if (el.dataset.primaryColor) overrides.primary = el.dataset.primaryColor;
const theme = { ...(config.theme || {}), ...overrides };
applyTheme(theme);
```

## 8. URL FETCH — lib/ai/urlFetch.ts
```ts
import dns from "node:dns/promises";
import http from "node:http";
import https from "node:https";
import { URL } from "node:url";

const TIMEOUT_MS = 10_000;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_REDIRECTS = 5;

function isPublicIpv4(ip: string): boolean {
  const p = ip.split(".").map(Number);
  if (p.length !== 4 || p.some((n) => Number.isNaN(n) || n < 0 || n > 255)) return false;
  const [a, b] = p;
  if (a === 0 || a === 10) return false;
  if (a === 127) return false;
  if (a === 169 && b === 254) return false;
  if (a === 172 && b >= 16 && b <= 31) return false;
  if (a === 192 && b === 168) return false;
  if (a === 100 && b >= 64 && b <= 127) return false;
  if (a >= 224) return false;
  return true;
}

function isPublicIpv6(ip: string): boolean {
  const l = ip.toLowerCase();
  if (l === "::" || l === "::1") return false;
  if (l.startsWith("fc") || l.startsWith("fd")) return false;
  if (l.startsWith("fe8") || l.startsWith("fe9") || l.startsWith("fea") || l.startsWith("feb")) return false;
  if (l.startsWith("ff")) return false;
  return true;
}

function assertPublicIp(ip: string): void {
  if (ip.toLowerCase().startsWith("::ffff:")) return assertPublicIp(ip.slice(7));
  const ok = ip.includes(":") ? isPublicIpv6(ip) : isPublicIpv4(ip);
  if (!ok) throw new Error("blocked non-public ip: " + ip);
}

function validateUrl(input: string): URL {
  let url: URL;
  try { url = new URL(input); } catch { throw new Error("invalid url"); }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("only http/https allowed");
  if (url.username || url.password) throw new Error("credentials not allowed");
  if (url.port && url.port !== "80" && url.port !== "443") throw new Error("nonstandard port blocked");
  return url;
}

async function resolvePublic(hostname: string): Promise<string> {
  const records = await dns.lookup(hostname, { all: true, verbatim: true });
  const ips = (Array.isArray(records) ? records : [{ address: records.address }]).map((r) => r.address);
  if (!ips.length) throw new Error("no dns records");
  for (const ip of ips) assertPublicIp(ip);
  return ips[0];
}

function requestOnce(target: URL, ip: string, timeoutMs: number): Promise<{ status: number; headers: http.IncomingHttpHeaders; body: Buffer }> {
  return new Promise((resolve, reject) => {
    const secure = target.protocol === "https:";
    const mod = secure ? https : http;
    const port = target.port ? Number(target.port) : secure ? 443 : 80;
    const req = mod.request({
      host: ip,
      port,
      path: target.pathname + target.search,
      method: "GET",
      headers: { Host: target.host, "User-Agent": "Mira/1.0", Accept: "text/html,application/xhtml+xml" },
      servername: secure ? target.hostname : undefined,
      lookup: (_h: string, _o: unknown, cb: (e: Error | null, a?: string, f?: number) => void) => cb(null, ip, ip.includes(":") ? 6 : 4),
      rejectUnauthorized: true,
    }, (res) => {
      const chunks: Buffer[] = [];
      let size = 0;
      res.on("data", (c: Buffer) => {
        size += c.length;
        if (size > MAX_BYTES) { req.destroy(new Error("response too large")); return; }
        chunks.push(c);
      });
      res.on("end", () => resolve({ status: res.statusCode ?? 0, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end();
  });
}

function htmlToText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">\").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/\s+/g, " ").trim().slice(0, 12000);
}

export async function urlFetch(rawUrl: string, opts: { timeoutMs?: number; maxRedirects?: number } = {}): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? TIMEOUT_MS;
  const maxRedirects = opts.maxRedirects ?? MAX_REDIRECTS;
  let current = validateUrl(rawUrl);
  for (let hop = 0; hop <= maxRedirects; hop++) {
    const ip = await resolvePublic(current.hostname);
    const { status, headers, body } = await requestOnce(current, ip, timeoutMs);
    if (status >= 300 && status < 400) {
      const loc = headers.location ? new URL(headers.location, current) : null;
      if (!loc) throw new Error("redirect without location");
      current = validateUrl(loc.toString());
      continue;
    }
    if (status >= 400) throw new Error("http " + status + " for " + current.href);
    return htmlToText(body.toString("utf8"));
  }
  throw new Error("too many redirects");
}
```

## 9. WIRE IT — in lib/chat/processMessage.ts
Register urlFetch as a tool the AI can call with a URL, server-side only, never exposed to the client widget. Each redirect hop re-validates DNS + IP so SSRF stays locked.

===