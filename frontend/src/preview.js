// Dev-only mount point — no build step, loaded directly by the browser as an
// ES module. While you build a screen, import your Presenter below and mount
// it in place of the placeholder. See
// docs/frontend-screens.md#preview-your-screen for the full workflow.
//
// Convention: a Presenter module exports `mount(container, props)`, which
// renders into `container` (e.g. via container.innerHTML = `...`) and wires
// up its own event listeners.
//
//   import { mount } from './Presenters/LifeList.js';
//   mount(document.getElementById('app'), { userId: 'u1' });

import { mount } from './Presenters/StickerShelf.js';

mount(document.getElementById('app'), { userId: 'u1' });
