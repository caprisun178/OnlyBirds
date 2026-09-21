// frontend/src/Presenters/Home.js -> shown to user / connection
// The signed-in home : welcome, a main call to action, and cards that
// lead to the other screens. There's no router yet, so navigation goes through
// an optional onNavigate callback (it just logs for now T).
import { renderHomeCard } from '../Components/HomeCard.js';

export function mount(container, props = {}) {
  const { onNavigate = (route) => console.log('navigate to:', route) } = props;

  container.innerHTML = `
    <div class="ob-container ob-stack">
      <header class="ob-stack">
        <h1>Welcome to Only Birds 🐦</h1>
        <p class="ob-text-muted">Spotted something? Describe it and earn stickers.</p>
      </header>

      <div>
        <button class="ob-btn ob-btn--primary ob-btn--lg" type="button" data-route="add-observation">
          Describe a bird
        </button>
      </div>

      <section class="ob-grid" aria-label="Where to next">
        ${renderHomeCard({
          title: 'Your life list',
          body: 'Every bird you have seen, and the ones still to find.',
          route: 'life-list',
          buttonLabel: 'Open life list',
        })}
        ${renderHomeCard({
          title: 'Your stickers ',
          body: 'Stickers you earn as you log new birds.',
          route: 'stickers',
          buttonLabel: 'View stickers',
          tag: 'Coming soon',
        })}
      </section>
    </div>
  `;



  container.querySelectorAll('[data-route]').forEach((el) => {
    el.addEventListener('click', () => onNavigate(el.dataset.route));
  });
}