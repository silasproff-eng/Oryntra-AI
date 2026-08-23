'use strict';

(() => {
  try {
    const preference = localStorage.getItem('oryntra_theme') || 'light';
    const appearanceQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const systemDark = appearanceQuery.matches;
    const resolved = preference === 'system' ? (systemDark ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = resolved === 'light' ? '#f5f8fb' : '#131d2a';
    if (preference === 'system') {
      appearanceQuery.addEventListener('change', (event) => {
        if ((localStorage.getItem('oryntra_theme') || 'light') !== 'system') return;
        const next = event.matches ? 'dark' : 'light';
        document.documentElement.dataset.theme = next;
        if (themeColor) themeColor.content = next === 'light' ? '#f5f8fb' : '#131d2a';
      });
    }
  } catch (_) {
    document.documentElement.dataset.theme = 'light';
    document.documentElement.dataset.themePreference = 'light';
  }
})();
