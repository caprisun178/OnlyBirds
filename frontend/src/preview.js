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

const app = document.getElementById('app');
app.innerHTML = `
  <h1>Only Birds — dev preview</h1>
  <p class="ob-text-muted">
    Nothing is mounted yet. Edit <code>frontend/src/preview.js</code> to
    import and mount the Presenter you're building.
  </p>
`;
