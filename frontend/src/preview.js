// Dev entry point — no build step, loaded directly by the browser as an ES
// module. There's still no real router (see docs/frontend-screens.md), but
// Home's cards need *something* to navigate to, so this is a minimal route
// switcher: it mounts Home by default and, for routes that lead to a screen
// that actually exists, tears down the current Presenter and mounts the
// next one in its place. Home itself is just a header (Life List, Add
// Observation, Login) with Explore Map embedded directly below it
// (`Presenters/Home.js` mounts `ExploreMap` in a sub-container with
// `embedded: true`) — so the app still opens straight into "start filtering
// birds," without a separate landing/marketing page, no route change
// needed to get there. Explore Map is deliberately NOT in `SCREENS` as its
// own route — Home *is* the Explore Map screen; a standalone `explore-map`
// route used to exist here too, reachable in parallel to Home, which read
// as two different home pages (a real "why did clicking a notification
// send me somewhere that isn't the app I was just using" report). Anything
// that wants to show the map — including a specific sighting from a
// notification — navigates to `home` and passes params through
// (`ExploreMap.js`'s own `focusObservationId` handling, forwarded by
// `Home.js`'s embedded mount). Routes with no screen yet just log, same as
// each screen's own default behavior. Sign-in (Google) gates the user-only
// screens — see SIGN_IN_REQUIRED below and Services/auth.js.
//
// Building a screen that isn't wired in below? Preview it on its own the old
// way — import its `mount` and call it directly instead of going through
// `navigate()`. See docs/frontend-screens.md#preview-your-screen.

import { mount as mountHome } from './Presenters/Home.js';
import { mount as mountAddObservation } from './Presenters/AddObservation.js';
import { mount as mountStickerShelf } from './Presenters/StickerShelf.js';
import { mount as mountLifeList } from './Presenters/LifeList.js';
import { mount as mountObservationList } from './Presenters/ObservationList.js';
import { mount as mountPlanATrip } from './Presenters/PlanATrip.js';
import { mount as mountNotificationsFeed } from './Presenters/NotificationsFeed.js';
import { mount as mountTestYourSkill } from './Presenters/TestYourSkill.js';
import { mount as mountBugBacklog } from './Presenters/BugBacklog.js';
import { mount as mountSpeciesPage } from './Presenters/SpeciesPage.js';
import { mount as mountProfile } from './Presenters/Profile.js';
import { mount as mountLogin } from './Presenters/Login.js';
import { mount as mountReportButton } from './Components/ReportButton.js';
import { authService, isAdmin, isSignedIn, onAuthChange } from './Services/auth.js';

const app = document.getElementById('app');

// Beta-only — present on every screen regardless of route, see
// Components/ReportButton.js for why this lives outside #app.
const reportWidget = mountReportButton();

const SCREENS = {
  home: (container, params) => mountHome(container, { onNavigate: navigate, ...params }),
  'add-observation': (container, params) => mountAddObservation(container, { onNavigate: navigate, ...params }),
  'life-list': (container, params) => mountLifeList(container, { onNavigate: navigate, ...params }),
  'observation-log': (container, params) => mountObservationList(container, { onNavigate: navigate, ...params }),
  stickers: (container, params) => mountStickerShelf(container, { onNavigate: navigate, ...params }),
  'plan-a-trip': (container, params) => mountPlanATrip(container, { onNavigate: navigate, ...params }),
  notifications: (container, params) => mountNotificationsFeed(container, { onNavigate: navigate, ...params }),
  'test-your-skill': (container, params) => mountTestYourSkill(container, { onNavigate: navigate, ...params }),
  'admin-bug-backlog': (container, params) => mountBugBacklog(container, { onNavigate: navigate, ...params }),
  'species-profile': (container, params) => mountSpeciesPage(container, { onNavigate: navigate, ...params }),
  profile: (container, params) => mountProfile(container, { onNavigate: navigate, ...params }),
  login: (container, params) => mountLogin(container, { onNavigate: navigate, ...params }),
};

// Screens that only make sense for a signed-in user (their own data). A
// signed-out visit goes to Login instead, which comes back here afterwards.
// Everything else (the map, species pages, Plan a Trip, Test Your Skill)
// works signed out, with its user-based bits hidden or disabled.
const SIGN_IN_REQUIRED = new Set([
  'add-observation',
  'life-list',
  'observation-log',
  'stickers',
  'notifications',
  'profile',
]);

// Admin screens: signed-in users whose email is in the server's
// ADMIN_EMAILS. Everyone else is sent to Home.
const ADMIN_ONLY = new Set(['admin-bug-backlog']);

let currentRoute = null;
let currentParams;

// `params` is an optional plain object spread onto the target screen's
// props — e.g. `onNavigate('observation-log', { scientificName, commonName })`
// from a Life List species card, to open that species' log pre-filtered.
function navigate(route, params) {
  const mountScreen = SCREENS[route];
  if (!mountScreen) {
    console.log('navigate to:', route, '(no screen yet)');
    return;
  }
  if ((SIGN_IN_REQUIRED.has(route) || ADMIN_ONLY.has(route)) && !isSignedIn()) {
    navigate('login', { next: route, nextParams: params });
    return;
  }
  if (ADMIN_ONLY.has(route) && !isAdmin()) {
    navigate('home');
    return;
  }
  currentRoute = route;
  currentParams = params;
  app.innerHTML = '';
  mountScreen(app, params);
  reportWidget.setScreen(route);
}

// Signed out (the Sign out button, or the session expiring mid-use): leave
// a user-only screen for the map, or remount any other screen so its
// user-based parts disappear. Sign-in doesn't need this: Login navigates
// onward itself.
onAuthChange((session) => {
  if (!currentRoute || currentRoute === 'login') return;
  if (!session && SIGN_IN_REQUIRED.has(currentRoute)) navigate('home');
  // Also covers admin status changing (authService.refresh() below): the
  // guard in navigate() moves a non-admin off an admin screen, and Home
  // re-renders with or without its Bug Backlog link.
  else navigate(currentRoute, currentParams);
});

navigate('home');
authService.refresh();
