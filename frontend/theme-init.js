// Runs before paint to avoid a theme flash.
(function () {
  var t = localStorage.getItem('vx_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', t);
})();
