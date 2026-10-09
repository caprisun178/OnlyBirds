# Progressive Web App (installable on a phone)

> **Status:** Planned, not started — scoped here so it can be picked up
> without re-litigating the two decisions already made: **PWA, not a native
> wrapper** (see rationale below), and **no in-app camera** — users upload
> photos they already took, same as [Add Observation](add-observation.md)
> does today. Revisit the native-wrapper decision only if a later
> requirement needs background location or push notifications while the
> app is fully closed (neither is true today).

## Why a PWA and not Capacitor/a native rewrite

The frontend is already a plain JS/HTML app with no build step
([Architecture](../architecture.md)) and already has the one meta tag that
matters (`viewport`, in both `index.html` and `src/preview.html`). A PWA —
a `manifest.json` plus a service worker — makes it installable (home-screen
icon, full-screen, no browser chrome) with no change to the app's
architecture and no app-store pipeline.

The usual reason to go further and wrap the app natively (Capacitor) is to
reach device APIs the browser doesn't expose — camera and background
location being the two that come up most. Neither applies here:

- **Camera** — deliberately out of scope. Users upload photos they took
  outside the app. A plain `<input type="file" accept="image/*">` already
  lets a phone's browser offer "Take Photo" or "Choose from Library" at the
  OS level — that's the device's file picker, not a native API this app
  needs to call.
- **Location** — [Explore Map](explore-map.md) and
  [Add Observation](add-observation.md)'s location picker only need a
  one-time "where is the user right now" read, which standard
  `navigator.geolocation` covers in every mobile browser. Nothing here
  needs continuous tracking while the app is in the background.

If one of those changes (e.g. background tracking for an auto-logging
feature), that's the trigger to reconsider Capacitor — not before, since it
adds a real build pipeline (Xcode/Android Studio, signing, store review)
this app doesn't otherwise need.

## 1. What you're building

- **`frontend/manifest.json`** — app name, icons, start URL, and
  `display: standalone` so the installed app opens without browser
  chrome (address bar, tabs).
- **A service worker** (`frontend/src/sw.js`) — caches the static shell
  (HTML/CSS/JS) so the app still *opens* with a flaky or absent
  connection. It must **not** cache API responses — bird sightings are
  live data, and a stale cached response would show the wrong thing.
- **App icons** — nothing to reuse here; there is no existing favicon or
  icon asset anywhere in `frontend/` today. This needs real art (a square
  mark, exported at 192×192 and 512×512, plus a "maskable" 512×512 variant
  for Android's adaptive-icon shape) before the manifest can point at
  anything. Not a code task — don't placeholder this with a generated icon
  and call it done.
- **Manifest/meta tags wired into the page the user actually installs
  from** — see the redirect note below for which file(s) that is.

Explicitly **not** part of this: a native wrapper, in-app photo capture,
background location, or push notifications while the app is closed (push
*while open*, i.e. in-tab, is a separate and much smaller ask if it comes
up — not scoped here).

## 2. What gets cached vs. what stays live

| Asset | Cached by the service worker? | Why |
|---|---|---|
| HTML/CSS/JS app shell (`preview.html`, `styles/base.css`, `src/**/*.js`) | Yes — cache-first, versioned cache name | So the app can open with no/poor connection |
| `manifest.json`, icons | Yes | Static, same reasoning |
| API calls (`/species/search`, `/sightings/nearby`, `/observations`, etc.) | **No** — passthrough to network, let it fail normally offline | Live bird data; a cached sighting list would silently go stale |
| Uploaded photos | Not a service-worker concern | Handled by Add Observation's existing upload flow |

A versioned cache name (e.g. `ob-shell-v1`, bumped on each deploy that
changes the shell) matters — without it, installed clients can get stuck
serving old JS after a deploy, since the service worker otherwise has no
other signal that the cached files changed.

## 3. Database changes

None. This is a frontend static-asset and deployment change only — no
backend, no migration.

## 4. Files touched

| File | Change |
|---|---|
| `frontend/manifest.json` | **New.** `name`, `short_name` ("Only Birds"), `icons`, `start_url`, `display: "standalone"`, `theme_color: "#3aa0ff"` (`--ob-blue-500`, the brand token in `styles/base.css`), `background_color: "#f4fbff"` (`--ob-mist`) |
| `frontend/icons/icon-192.png`, `icon-512.png`, `icon-512-maskable.png` | **New.** Needs source art — see §1 |
| `frontend/src/sw.js` | **New.** Cache-first for the shell, explicit network-only passthrough for anything hitting the backend API origin |
| `frontend/src/preview.html` | Add `<link rel="manifest">`, `<meta name="theme-color">`, `<link rel="apple-touch-icon">` |
| `frontend/src/preview.js` | Register the service worker on load (`navigator.serviceWorker.register('./sw.js')`) |
| `frontend/index.html` | See redirect note below — may need the same tags, or may not |

### The redirect page needs a decision, not an assumption

`frontend/index.html` is a meta-refresh redirect straight to
`src/preview.html` (see its own comment — this exists for the GitHub Pages
deploy and local `python -m http.server` root hit). A browser's
"install/add to home screen" affordance reads the manifest linked from
whatever page is currently loaded. Since the redirect immediately hands
the user off to `preview.html`, that's almost certainly the only page that
needs the manifest link — but confirm this against the actual install
prompt on at least one Android/Chrome device while building, rather than
assuming; if the redirect's timing ever interferes with the install
prompt on a given browser, `index.html` would need its own manifest link
as a fallback.

## 5. Build order

1. Get real icon art — a square mark, 512×512 source, exported to 192/512
   PNG plus a maskable 512×512 variant. Blocks everything else.
2. Write `frontend/manifest.json`.
3. Link the manifest + meta tags from `src/preview.html`.
4. Write `frontend/src/sw.js` — cache-first shell, versioned cache name,
   explicit no-cache passthrough for the API origin.
5. Register the service worker in `preview.js`.
6. Verify installability: Chrome DevTools → Application tab → Manifest +
   Service Workers panels show no errors.
7. Test the real install flow on an actual phone — Android/Chrome (install
   prompt) and iOS/Safari (manual "Add to Home Screen" from the share
   sheet; iOS has no automatic prompt).
8. Test offline: airplane mode, reopen the installed app. The shell should
   load; check what the `Dao`/`Services` layers currently do when a fetch
   fails (reuse whatever error handling already exists rather than adding
   a new "offline" UI state, unless there genuinely isn't one to reuse).
9. Deploy, then confirm a second deploy actually invalidates the old
   cached shell for a client that already installed the app (this is what
   the versioned cache name in step 4 is for — confirm it, don't just
   assume it works).

## Related pages

- [Building a screen](../frontend-screens.md) — where `preview.js` /
  `preview.html` live and how routing works today
- [Deployment](../deployment.md) — the static host (Vercel/Netlify/GitHub
  Pages) already serves over HTTPS, which service workers require; nothing
  to change there
- [Add Observation](add-observation.md) — the upload-only photo flow this
  page relies on instead of native camera access
- [Explore map](explore-map.md) — the location picker this page relies on
  standard browser geolocation for, instead of a native location API
