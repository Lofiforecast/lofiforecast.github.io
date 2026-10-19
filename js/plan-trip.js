(function () {
  var form = document.getElementById('plan-form');
  var q = document.getElementById('city-q');
  var monthEl = document.getElementById('month');
  var list = document.getElementById('city-list');
  var suggest = document.getElementById('suggest');
  var result = document.getElementById('plan-result');
  var outlook = document.getElementById('outlook');
  var climateText = document.getElementById('climate-text');
  var packList = document.getElementById('pack-list');
  var resTitle = document.getElementById('res-title');
  var resNow = document.getElementById('res-now');
  var planSrc = document.getElementById('plan-src');
  var forecast = null, climate = null;

  monthEl.value = String(new Date().getMonth() + 1);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function packTips(hi, lo, rainMm, rainNote) {
    var tips = [];
    var mid = (hi + lo) / 2;
    if (hi >= 30) tips.push('Light breathable layers', 'Sunscreen', 'Hat / shade');
    else if (hi >= 22) tips.push('Light layers', 'Comfortable daywear');
    else if (hi >= 15) tips.push('Light jacket or cardigan', 'Layers for cool evenings');
    else if (hi >= 8) tips.push('Warm jacket', 'Long pants', 'Closed shoes');
    else tips.push('Coat / insulated layer', 'Warm base layers', 'Gloves if windy');
    if (lo <= 10 && hi >= 18) tips.push('Day–night swing: pack a warmer layer');
    if ((rainMm != null && rainMm >= 80) || (rainNote && /wet|showery/i.test(rainNote))) tips.push('Rain jacket', 'Waterproof shoes');
    else if (rainMm != null && rainMm >= 40) tips.push('Compact umbrella or light rain shell');
    if (hi >= 28 && rainMm != null && rainMm < 40) tips.push('Stay hydrated');
    // dedupe
    var seen = {}, out = [];
    tips.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
    return out.slice(0, 6);
  }

  function findCity(query) {
    if (!forecast || !query) return null;
    var n = query.trim().toLowerCase();
    var cities = forecast.cities || [];
    var exact = cities.find(function (c) { return c.name.toLowerCase() === n || c.id === n; });
    if (exact) return exact;
    return cities.find(function (c) {
      return c.name.toLowerCase().indexOf(n) === 0 ||
        (c.country && c.country.toLowerCase().indexOf(n) === 0);
    }) || cities.find(function (c) {
      return c.name.toLowerCase().indexOf(n) >= 0;
    });
  }

  function dayCard(d) {
    var dt = new Date(d.date + 'T12:00:00Z');
    var dow = dt.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' }).toUpperCase();
    var dnum = dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }).toUpperCase();
    return (
      '<li class="day" title="' + esc(d.condition || '') + '">' +
        '<div class="day-head"><span class="dow">' + esc(dow) + '</span><span class="dnum">' + esc(dnum) + '</span></div>' +
        '<div class="day-temps"><b>' + esc(d.high_c) + '°</b><span>' + esc(d.low_c) + '°</span></div>' +
        '<div class="day-cond">' + esc(d.condition || '') + '</div>' +
        (d.precip_mm != null ? '<div class="day-psr">Rain ~' + esc(d.precip_mm) + ' mm</div>' : '') +
      '</li>'
    );
  }

  function show(city) {
    if (!city) return;
    result.classList.add('is-on');
    resTitle.textContent = city.name;
    document.getElementById('res-eyebrow').textContent = city.country || 'Outlook';
    var t = city.today || {};
    resNow.textContent =
      (city.temp_c != null ? 'Now about ' + city.temp_c + '°C · ' : '') +
      (city.condition || '') +
      (t.high_c != null ? ' · Today ' + t.high_c + '° / ' + t.low_c + '°' : '');
    var days = (city.days || []).slice(0, 14);
    outlook.innerHTML = days.map(dayCard).join('');
    outlook.style.gridTemplateColumns = 'repeat(' + Math.min(8, Math.max(4, days.length)) + ',minmax(0,1fr))';

    var mo = monthEl.value;
    var climCity = climate && climate.cities && climate.cities[city.id];
    var m = climCity && climCity.months && climCity.months[mo];
    var monthName = monthEl.options[monthEl.selectedIndex].text;
    if (m) {
      climateText.innerHTML =
        'In <b>' + esc(monthName) + '</b>, ' + esc(city.name) + ' is typically around ' +
        '<b>' + esc(m.typical_high_c) + '°</b> high / <b>' + esc(m.typical_low_c) + '°</b> low' +
        (m.typical_precip_mm != null ? ', with about <b>' + esc(m.typical_precip_mm) + ' mm</b> of rain for the month' : '') +
        '. ' + esc(m.rain_note || '') +
        '<br><small style="color:var(--muted)">Based on 2015–2019 monthly averages (Open-Meteo / ERA5). This is climate, not a prediction for a specific day.</small>';
      packList.innerHTML = packTips(m.typical_high_c, m.typical_low_c, m.typical_precip_mm, m.rain_note)
        .map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('');
    } else {
      climateText.textContent = 'No climate table for this city yet — use the near-term strip above.';
      packList.innerHTML = '';
    }
    planSrc.textContent =
      'Outlook: MET Norway Locationforecast · Climate: Open-Meteo archive · Music & brand: Temple Street / Lofi Forecast · Made possible by Weather Bot';
    document.querySelectorAll('.suggest button').forEach(function (b) {
      b.classList.toggle('is-on', b.dataset.id === city.id);
    });
    q.value = city.name;
  }

  function wireSuggest(cities) {
    suggest.innerHTML = '';
    cities.slice(0, 12).forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.id = c.id;
      b.textContent = c.name;
      b.addEventListener('click', function () { show(c); });
      suggest.appendChild(b);
    });
    list.innerHTML = cities.map(function (c) {
      return '<option value="' + esc(c.name) + '">' + esc(c.country) + '</option>';
    }).join('');
  }

  Promise.all([
    fetch('world-forecast.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }),
    fetch('climate-normals.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }),
  ]).then(function (pair) {
    forecast = pair[0];
    climate = pair[1];
    wireSuggest(forecast.cities || []);
    var params = new URLSearchParams(location.search);
    var start = findCity(params.get('city') || 'Hong Kong') || (forecast.cities || [])[0];
    if (params.get('month')) monthEl.value = params.get('month');
    if (start) show(start);
  }).catch(function (err) {
    suggest.innerHTML = '<li style="color:var(--rust)">Could not load data: ' + esc(err.message) + '</li>';
  });

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var city = findCity(q.value);
    if (!city) {
      resTitle.textContent = 'Not in the list yet';
      resNow.textContent = 'Try one of the quick picks, or a World Weather city name. Free geocoding for any place comes next.';
      result.classList.add('is-on');
      outlook.innerHTML = '';
      return;
    }
    show(city);
  });
  monthEl.addEventListener('change', function () {
    var city = findCity(q.value);
    if (city) show(city);
  });
})();
