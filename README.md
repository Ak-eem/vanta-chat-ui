PS C:\Users\User\Desktop\MIRA\mira\Mira-main> npx vercel inspect dpl_DHA5MDPFjysmkYGCdaTmSBfXsu17 --logs
Need to install the following packages:
vercel@59.11.2
Ok to proceed? (y) y
npm warn deprecated stream-to-promise@2.2.0: Deprecated. Use node:stream/promises and node:stream/consumers instead.
npm warn deprecated tar@7.5.7: Old versions of tar are not supported, and contain widely publicized security vulnerabilities, which have been fixed in the current version. Please update. Support for old versions may be purchased (at exorbitant rates) by contacting i@izs.me
Vercel CLI 59.11.2 (Node.js 24.16.0)
> NOTE: The Vercel CLI now collects telemetry regarding usage of the CLI.
> This information is used to shape the CLI roadmap and prioritize features.
> You can learn more, including how to opt-out if you'd not like to participate in this program, by visiting the following URL:
> https://vercel.com/docs/cli/about-telemetry
> No existing credentials found. Please log in:
> 
  Visit https://vercel.com/oauth/device?user_code=JMKW-FVDX
> Success! Logged in.
2026-09-02T15:50:49.747Z  Running build in Washington, D.C., USA (East) – iad1
2026-09-02T15:50:49.748Z  Build machine configuration: 2 cores, 8 GB
2026-09-02T15:50:49.932Z  Cloning github.com/Ak-eem/Mira (Branch: main, Commit: 6aff5cb)
2026-09-02T15:50:50.726Z  Cloning completed: 794.000ms
2026-09-02T15:50:51.079Z  Restored build cache from previous deployment (QSjT5ar2bsiSsNkRaZiCY4849Fuy)
2026-09-02T15:50:51.360Z  Running "vercel build"
2026-09-02T15:50:51.381Z  Vercel CLI 59.11.0
2026-09-02T15:50:51.576Z  Installing dependencies...
2026-09-02T15:50:52.774Z  
2026-09-02T15:50:52.775Z  up to date in 1s
2026-09-02T15:50:52.775Z  
2026-09-02T15:50:52.775Z  156 packages are looking for funding
2026-09-02T15:50:52.775Z  run `npm fund` for details
2026-09-02T15:50:52.776Z  npm warn allow-scripts 1 package has install scripts not yet covered by allowScripts:
2026-09-02T15:50:52.776Z  npm warn allow-scripts   unrs-resolver@1.12.2 (postinstall: node postinstall.js)
2026-09-02T15:50:52.777Z  npm warn allow-scripts
2026-09-02T15:50:52.777Z  npm warn allow-scripts Run `npm approve-scripts --allow-scripts-pending` to review, or `npm approve-scripts <pkg>` to allow.
2026-09-02T15:50:52.806Z  Detected Next.js version: 16.3.0
2026-09-02T15:50:52.813Z  Running "npm run build"
2026-09-02T15:50:52.920Z  
2026-09-02T15:50:52.920Z  > mira@0.1.0 build
2026-09-02T15:50:52.920Z  > next build
2026-09-02T15:50:52.920Z  
2026-09-02T15:50:53.427Z  ▲ Next.js 16.3.0 (Turbopack)
2026-09-02T15:50:53.536Z  Applying modifyConfig from Vercel
2026-09-02T15:50:53.539Z  ✓ Running next.config.js took 112ms
2026-09-02T15:50:53.645Z  
2026-09-02T15:50:53.685Z  Creating an optimized production build ...
2026-09-02T15:50:59.987Z  ✓ Compiled successfully in 5.4s
2026-09-02T15:50:59.990Z  Running TypeScript ...
2026-09-02T15:51:03.408Z  lib/chat/processMessage.ts(99,7): error TS2741: Property 'last_message_at' is missing in type '{ id: any; business_id: any; }' but required in type '{ id: any; business_id: any; last_message_at: any; }'.
2026-09-02T15:51:03.409Z  lib/chat/processMessage.ts(104,7): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.409Z  lib/chat/processMessage.ts(111,28): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.409Z  lib/chat/processMessage.ts(120,22): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.409Z  lib/chat/processMessage.ts(140,28): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(157,19): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(188,17): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(203,26): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(220,17): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(253,24): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.410Z  lib/chat/processMessage.ts(270,15): error TS18047: 'conversation' is possibly 'null'.
2026-09-02T15:51:03.427Z  Failed to type check.
2026-09-02T15:51:03.427Z  
2026-09-02T15:51:03.476Z  Error: Command "npm run build" exited with 1
status  ● Error
