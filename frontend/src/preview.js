// Dev entry point — no build step, loaded directly by the browser as an ES
// module. There's still no real router (see docs/frontend-screens.md), but
// Home's cards need *something* to navigate to, so this is a minimal route
// switcher: it mounts Home by default (no landing/marketing page — Home is
// the app's front door) and, for routes that lead to a screen that actually
// exists, tears down the current Presenter and mounts the next one in its
// place. Routes with no screen yet just log, same as each screen's own
// default behavior. Auth/login is separate in-progress work — not wired in
// here yet.
//
// Building a screen that isn't wired in below? Preview it on its own the old
// way — import its `mount` and call it directly instead of going through
// `navigate()`. See docs/frontend-screens.md#preview-your-screen.

import { mount as mountHome } from './Presenters/Home.js';
import { mount as mountAddObservation } from './Presenters/AddObservation.js';
import { mount as mountLifeList } from './Presenters/LifeList.js';

const app = document.getElementById('app');

const SCREENS = {
  home: (container) => mountHome(container, { onNavigate: navigate }),
  'add-observation': (container) => mountAddObservation(container, { onNavigate: navigate }),
  'life-list': (container) => mountLifeList(container, { onNavigate: navigate }),
};

function navigate(route) {
  const mountScreen = SCREENS[route];
  if (!mountScreen) {
    console.log('navigate to:', route, '(no screen yet)');
    return;
  }
  app.innerHTML = '';
  mountScreen(app);
}

navigate('home');
