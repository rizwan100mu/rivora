// Keep the explicit mobile language on same-origin Frappe AJAX requests.
// The site's own form engine and Client Scripts remain responsible for behavior.
(() => {
  const parameters = new URLSearchParams(location.search);
  const language = parameters.get('_lang');
  if (parameters.get('_rivora_mobile') !== '1' || !['en','ar','hi','ur'].includes(language)) return;
  if (window.jQuery) {
    jQuery.ajaxPrefilter((options) => {
      const url = new URL(options.url, location.href);
      if (url.origin === location.origin) {
        url.searchParams.set('_lang', language);
        options.url = url.toString();
      }
    });
  }
})();
