== SECTION A: Fixes for feature/admin-nav-restructure (Ak-eem/Mira) ==
1. Subscription counts: count DISTINCT businesses not rows (SQL group by business_id, take latest subscription per business).
2. Silent query failures: every Supabase query on admin pages must surface errors (toast or inline error state), never render zeroes on failure.
3. Security: business-scoped layout must check entitlement BEFORE fetching/rendering business data; verify RLS permits platform admins and blocks unauthorized businessIds; never trust client-side business IDs. Include test list (authorized admin, non-admin user, random businessId, deleted business).
4. Pagination (page size ~20) for flagged conversations and business list.
5. Mobile: sidebars need responsive drawer/collapse.
6. Fragile pathname matching: replace with route-map helper.

== SECTION B: Phase 3 spec — Mira Analytics + Business Analytics ==
Based on the master spec in vanta-dashboard-ui README:
- Strict separation: Mira Analytics (platform-level, admin only) vs Business Analytics (inside /admin/businesses/[businessId]/analytics, scoped by business_id, RLS-respecting).
- Data layer: lib/analytics/ service functions getPlatformAnalytics(range) and getBusinessAnalytics(businessId, range); date filters today/7d/30d/this month/custom; aggregate via SQL (counts, success/failure rates, avg latency, Groq vs Gemini usage, escalations) from existing tables (conversations, messages, activity_log, businesses, business_subscriptions). If a metric cannot be computed from existing schema, define exact table/column needed as a required migration, do NOT fabricate data.
- UI: metric cards, charts (messages over time, AI responses, success vs failed, provider usage, response time, escalations), business activity table, system health badges (Operational/Degraded/Unavailable/Needs attention), skeleton loaders, empty states, error states.
- Rules: no mixing platform and business analytics, no hardcoded values, server-side authorization, reuse glass-panel/Tailwind design system.
- Output checklist: files to create/modify, routes, migrations, env vars, testing steps.