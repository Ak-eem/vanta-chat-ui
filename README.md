I’ll walk through the resolved merge changes file by file, starting with the four conflict surfaces and the exact staged diff. I’ll explain each changed block in plain language, including why both branches’ behavior remains present.

Ran terminal command: git diff --cached --unified=3 -- "app/admin/(protected)/AnalyticsPanel.tsx" "app/admin/(protected)/businesses/[businessId]/conversations/page.tsx" "app/admin/(protected)/businesses/[businessId]/conversations/[conversationId]/page.tsx" "lib/analytics/queries.ts"

Read , lines 1 to 280

Here is the resolved diff explained by changed block.

**AnalyticsPanel.tsx/`AnalyticsPanel.tsx`)**

- Added `getSystemHealth` import.
- Changed `AnalyticsPanel` to `async` because it now awaits live health data.
- Added `const systemHealth = await getSystemHealth()`.
- Replaced hardcoded `"Operational"` labels with:
  - `systemHealth.database.status`
  - `systemHealth.aiProvider.status`
  - `systemHealth.backgroundJobs.status`
- Added timestamps showing when each health check ran.
- Changed `snapshot.unansweredQuestions` to `snapshot.recentUnansweredQuestions` because the fix branch uses `unansweredQuestions` for a different aggregate structure.

**conversations/page.tsx/businesses/[businessId]/conversations/page.tsx)**

- Added `owner_read_at` to the selected conversation fields.
- Changed the unread filter from only `is_unread = true` to:
  - legacy unread flag: `is_unread = true`
  - or fix-branch unread state: `owner_read_at IS NULL`
- Added `isUnread`, which combines both systems.
- The unread dot now uses the combined value.
- Added the visible `Unread` label while retaining the original unread dot.
- Converted the `.map()` callback to a block so `isUnread` can be calculated once per conversation.

**[conversation detail page](app/admin/(protected)/businesses/[businessId]/conversations/[conversationId]/page.tsx)**

- Added `owner_read_at` to the conversation query.
- Kept `last_viewed_at` updates from `main`.
- Added an owner-read update when `owner_read_at` is missing.
- The update is scoped by both conversation ID and business ID.
- `.is("owner_read_at", null)` prevents overwriting a newer read state.

**`queries.ts`**

- Added shared types:
  - `CountInsight`
  - `UnansweredInsight`
  - `RateInsight`
- Kept `popularProducts` from `main`.
- Renamed the old recent-question array to `recentUnansweredQuestions`.
- Added the fix branch’s aggregate fields:
  - `popularQuestions`
  - `topProducts`
  - aggregate `unansweredQuestions`
  - `resolutionRate`
  - `reopenRate`
- When a business is selected, the code now loads all five business insights in parallel.
- Preserved the existing RPC-based product and recent-question data.
- Added helpers to:
  - normalize question text
  - count and sort repeated questions
  - calculate the requested date range
- `getPopularQuestions()` counts customer messages.
- `getTopProducts()` combines product-interest records with product-name mentions in customer messages.
- `getUnansweredQuestions()` detects fallback assistant replies and associates them with the previous customer question.
- `getResolutionRate()` compares closed conversations with total conversations.
- `getReopenRate()` detects conversations reopened after previously being closed.

The remaining staged files were non-conflicting additions from the fix branch, including system-health APIs, RLS migration `0033`, asset-policy migration `0034`, URL fetching, and the business insights component.
