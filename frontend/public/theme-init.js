// Applies the saved theme before first paint (no flash). A file, not an inline script, so the
// Content-Security-Policy can forbid inline scripts. The dark terminal theme is the default.
try {
  if (localStorage.getItem('echo-theme') !== 'light') document.documentElement.classList.add('dark')
} catch (e) {
  document.documentElement.classList.add('dark')
}
