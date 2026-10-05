// Lofi Forecast HK: live HKT clock, Spotify embed with styled fallback, mood switcher, copy data line,
// and in-place freshness: every 10 min re-read /forecast.json; if the hourly rebuild is late (>90 min),
// read the current reading + warnings straight from the HKO open data API (CORS-enabled) instead.
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var clock = $('hkt-clock');
  function hkt(d, opts) {
    return new Intl.DateTimeFormat('en-GB', Object.assign({timeZone: 'Asia/Hong_Kong'}, opts)).format(d);
  }
  function tick() { try { clock.textContent = hkt(new Date(), {hour: '2-digit', minute: '2-digit', hour12: false}); } catch (e) {} }
  if (clock) { tick(); setInterval(tick, 15000); }

  // ---------------- Spotify embed (styled fallback stays visible unless the iframe actually loads)
  var embed = $('embed'), frame = $('sp-embed');
  var params = new URLSearchParams(location.search);
  var embedOn = params.get('embed') !== 'off';
  function loadEmbed(pid) {
    if (!embedOn || !frame) return;
    embed.classList.remove('is-live');
    frame.onload = function () { setTimeout(function () { if (frame.src.indexOf(pid) > -1) embed.classList.add('is-live'); }, 8000); };
    frame.src = 'https://open.spotify.com/embed/playlist/' + pid + '?utm_source=generator&theme=0';
  }
  window.addEventListener('message', function (ev) {
    if (ev.origin === 'https://open.spotify.com' && ev.data && ev.data.type === 'ready') embed.classList.add('is-live');
  });
  if (embed) loadEmbed(embed.dataset.pid);

  function pick(a, ev) {
    ev.preventDefault();
    document.querySelectorAll('.mood.is-on').forEach(function (m) { m.classList.remove('is-on'); });
    if (a.classList.contains('mood')) a.classList.add('is-on');
    var m = a.dataset.mood, label = m === 'Radio' ? 'Lofi Forecast Radio' : m;
    $('np-mood').textContent = label;
    $('np-blurb').textContent = a.dataset.blurb;
    $('fb-title').textContent = label;
    $('fb-cover').src = a.dataset.cover;
    $('embed-fallback').href = a.href;
    document.documentElement.style.setProperty('--mood', a.dataset.accent);
    if (frame) frame.title = 'Spotify playlist: ' + label;
    loadEmbed(a.dataset.pid);
  }
  document.querySelectorAll('.mood, .radio-card').forEach(function (a) {
    a.addEventListener('click', function (ev) { pick(a, ev); });
  });

  var btn = $('copy-line');
  if (btn && navigator.clipboard) {
    btn.addEventListener('click', function () {
      navigator.clipboard.writeText($('data-line').textContent).then(function () {
        btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = 'Copy'; }, 1600);
      });
    });
  }

  // ---------------- freshness
  var ICON = {50: 'Sunny', 51: 'Sunny periods', 52: 'Sunny intervals', 53: 'Sunny periods, showers', 54: 'Sunny intervals, showers',
    60: 'Cloudy', 61: 'Overcast', 62: 'Light rain', 63: 'Rain', 64: 'Heavy rain', 65: 'Thunderstorms', 70: 'Fine', 71: 'Fine',
    72: 'Fine', 73: 'Fine', 74: 'Fine', 75: 'Fine', 76: 'Mainly cloudy', 77: 'Mainly fine', 80: 'Windy', 81: 'Dry', 82: 'Humid',
    83: 'Fog', 84: 'Mist', 85: 'Haze', 90: 'Hot', 91: 'Warm', 92: 'Cool', 93: 'Cold'};
  var SEV = {WRAINA: 'amber', WRAINR: 'red', WRAINB: 'black', TC1: 'tc-low', TC3: 'tc-mid', TC8NE: 'tc-high', TC8SE: 'tc-high',
    TC8SW: 'tc-high', TC8NW: 'tc-high', TC9: 'tc-high', TC10: 'tc-high', WHOT: 'hot', WCOLD: 'cold', WFROST: 'cold', WTS: 'amber'};
  var shownObs = document.body.dataset.obs;
  var HKO = 'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?lang=en&dataType=';
  function hhmm(iso) { return hkt(new Date(iso), {hour: '2-digit', minute: '2-digit', hour12: false}); }
  function setText(sel, txt) { document.querySelectorAll(sel).forEach(function (n) { n.textContent = txt; }); }
  function chip(cls, txt) { var s = document.createElement('span'); s.className = 'chip ' + cls; s.textContent = txt; return s; }
  function apply(r, live) {   // r = {obs, temp, rh, cond, warnings:[{code,title}]}
    if (!r || !r.obs || new Date(r.obs) <= new Date(shownObs)) return;
    shownObs = r.obs;
    if (r.temp != null) $('js-temp').textContent = r.temp;
    if (r.rh != null) $('js-rh').textContent = r.rh;
    if (r.cond) $('js-cond').textContent = r.cond.toUpperCase();
    setText('.js-obs', hhmm(r.obs));
    var w = $('js-warn');
    if (r.warnings) {
      w.textContent = '';
      if (!r.warnings.length) w.appendChild(chip('chip-ok', 'No weather warnings in force'));
      r.warnings.forEach(function (x) { w.appendChild(chip('chip-warn sev-' + (SEV[x.code] || 'other'), '\u26A0 ' + x.title)); });
    }
    if (live) w.appendChild(chip('chip-live', 'Live from HKO ' + hhmm(r.obs) + ' HKT'));
  }
  function getJSON(u) { return fetch(u, {cache: 'no-store'}).then(function (r) { if (!r.ok) throw r.status; return r.json(); }); }
  function fromFeed(f) {
    return {obs: f.current.obs_time, temp: f.current.temp_c, rh: f.current.humidity_pct, cond: f.current.condition,
      warnings: f.warnings.in_force.map(function (x) { return {code: x.code, title: x.title || x.name || x.code}; })};
  }
  function fromHKO() {
    return Promise.all([getJSON(HKO + 'rhrread'), getJSON(HKO + 'warnsum')]).then(function (a) {
      var rh = a[0], ws = a[1] || {};
      var t = (rh.temperature.data || []).filter(function (x) { return x.place === 'Hong Kong Observatory'; })[0];
      var h = (rh.humidity.data || []).filter(function (x) { return x.place === 'Hong Kong Observatory'; })[0];
      var warns = Object.keys(ws).map(function (k) { return ws[k]; }).filter(function (v) { return v && v.actionCode !== 'CANCEL'; })
        .map(function (v) { return {code: v.code, title: (v.type && v.name.indexOf(v.type) < 0 ? v.type + ' ' : '') + v.name}; });
      return {obs: rh.updateTime, temp: t && t.value, rh: h && h.value, cond: ICON[(rh.icon || [])[0]], warnings: warns};
    });
  }
  function refresh() {
    getJSON('forecast.json?t=' + Date.now()).then(function (f) {
      apply(fromFeed(f), false);
      if (Date.now() - new Date(f.generated_at) > 90 * 60000) return fromHKO().then(function (r) { apply(r, true); });
    }).catch(function () { fromHKO().then(function (r) { apply(r, true); }).catch(function () {}); });
  }
  if (params.get('live') !== 'off') {
    if (Date.now() - new Date(document.body.dataset.generated) > 90 * 60000) refresh();
    setInterval(refresh, 10 * 60000);
  }
})();
