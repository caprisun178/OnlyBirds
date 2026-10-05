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
// needed to get there. `explore-map` stays in `SCREENS` too, so it's still
// reachable as its own standalone route (with its own `<h1>` and "← Back to
// home"), same as before. Routes with no screen yet just log, same as each
// screen's own default behavior. Auth/login is separate in-progress work —
// not wired in here yet.
//
// Building a screen that isn't wired in below? Preview it on its own the old
// way — import its `mount` and call it directly instead of going through
// `navigate()`. See docs/frontend-screens.md#preview-your-screen.

import { mount as mountHome } from './Presenters/Home.js';
import { mount as mountAddObservation } from './Presenters/AddObservation.js';
import { mount as mountLifeList } from './Presenters/LifeList.js';
import { mount as mountObservationList } from './Presenters/ObservationList.js';
import { mount as mountExploreMap } from './Presenters/ExploreMap.js';
import { mount as mountPlanATrip } from './Presenters/PlanATrip.js';

const app = document.getElementById('app');

const SCREENS = {
  home: (container, params) => mountHome(container, { onNavigate: navigate, ...params }),
  'add-observation': (container, params) => mountAddObservation(container, { onNavigate: navigate, ...params }),
  'life-list': (container, params) => mountLifeList(container, { onNavigate: navigate, ...params }),
  'observation-log': (container, params) => mountObservationList(container, { onNavigate: navigate, ...params }),
  'explore-map': (container, params) => mountExploreMap(container, { onNavigate: navigate, ...params }),
  'plan-a-trip': (container, params) => mountPlanATrip(container, { onNavigate: navigate, ...params }),
};

// `params` is an optional plain object spread onto the target screen's
// props — e.g. `onNavigate('observation-log', { scientificName, commonName })`
// from a Life List species card, to open that species' log pre-filtered.
function navigate(route, params) {
  const mountScreen = SCREENS[route];
  if (!mountScreen) {
    console.log('navigate to:', route, '(no screen yet)');
    return;
  }
  app.innerHTML = '';
  mountScreen(app, params);
}

navigate('home');
