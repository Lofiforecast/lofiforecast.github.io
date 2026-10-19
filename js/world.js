(function () {
  var grid = document.getElementById('city-grid');
  var src = document.getElementById('cities-src');
  var week = document.getElementById('ww-week');
  var yt = document.getElementById('ww-yt');
  var video = document.getElementById('ww-video');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function card(c) {
    var t = c.today || {};
    var hi = t.high_c != null ? t.high_c : '–';
    var lo = t.low_c != null ? t.low_c : '–';
    var now = c.temp_c != null ? c.temp_c : hi;
    return (
      '<li class="city-card">' +
        '<div class="cc-head"><p class="cc-name">' + esc(c.name) + '</p>' +
        '<div class="cc-country">' + esc(c.country) + '</div></div>' +
        '<div class="cc-body"><div class="cc-temp">' + esc(now) + '<sup>°C</sup></div>' +
        '<div class="cc-hl"><b>' + esc(hi) + '°</b> / <span>' + esc(lo) + '°</span></div></div>' +
        '<div class="cc-cond">' + esc(c.condition || t.condition || '') + '</div>' +
      '</li>'
    );
  }

  fetch('world-forecast.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error('forecast ' + r.status); return r.json(); })
    .then(function (data) {
      var ww = (data.ww_ids || []).length
        ? data.cities.filter(function (c) { return data.ww_ids.indexOf(c.id) >= 0; })
        : data.cities.filter(function (c) { return c.ww; });
      if (!ww.length) ww = data.cities.slice(0, 12);
      grid.innerHTML = ww.map(card).join('');
      if (data.week_label && week) week.textContent = 'Week of ' + data.week_label;
      if (data.youtube && yt) yt.href = data.youtube;
      if (data.video && video) {
        video.src = data.video;
        if (data.poster) video.poster = data.poster;
      }
      var fetched = data.fetched_utc ? new Date(data.fetched_utc) : null;
      var when = fetched
        ? fetched.toLocaleString('en-GB', { timeZone: 'Asia/Hong_Kong', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) + ' HKT'
        : '';
      src.textContent = 'Weather data: MET Norway' + (when ? ' · built ' + when : '');
      // try autoplay muted loop
      if (video) {
        var p = video.play();
        if (p && p.catch) p.catch(function () {});
      }
    })
    .catch(function (err) {
      grid.innerHTML = '<li class="city-card"><div class="cc-head"><p class="cc-name">Unavailable</p></div><div class="cc-cond" style="padding:14px">Could not load world-forecast.json</div></li>';
      src.textContent = 'Weather data: MET Norway · ' + err.message;
    });
})();
