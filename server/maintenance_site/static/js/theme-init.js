'use strict';

(() => {
  try {
    const preference = localStorage.getItem('oryntra_theme') || 'system';
    const appearanceQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const systemDark = appearanceQuery.matches;
    const resolved = preference === 'system' ? (systemDark ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = resolved === 'light' ? '#d4dce5' : '#080d14';
    if (preference === 'system') {
      appearanceQuery.addEventListener('change', (event) => {
        if ((localStorage.getItem('oryntra_theme') || 'system') !== 'system') return;
        const next = event.matches ? 'dark' : 'light';
        document.documentElement.dataset.theme = next;
        if (themeColor) themeColor.content = next === 'light' ? '#d4dce5' : '#080d14';
      });
    }
  } catch (_) {
    document.documentElement.dataset.theme = 'dark';
    document.documentElement.dataset.themePreference = 'system';
  }
})();
