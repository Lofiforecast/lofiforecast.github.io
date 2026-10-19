(function () {
  var form = document.getElementById('plan-form');
  var q = document.getElementById('city-q');
  var monthEl = document.getElementById('month');
  var list = document.getElementById('city-list');
  var suggest = document.getElementById('suggest');
  var geoDrop = document.getElementById('geo-drop');
  var statusEl = document.getElementById('plan-status');
  var result = document.getElementById('plan-result');
  var outlook = document.getElementById('outlook');
  var climateText = document.getElementById('climate-text');
  var packList = document.getElementById('pack-list');
  var resTitle = document.getElementById('res-title');
  var resNow = document.getElementById('res-now');
  var planSrc = document.getElementById('plan-src');
  var forecast = null, climate = null;
  var activePlace = null; // last shown place (seeded or geocoded)
  var climateCache = {}; // "lat,lon" -> { months: { "1": {...}, ... } }

  monthEl.value = String(new Date().getMonth() + 1);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function setStatus(msg) {
    statusEl.textContent = msg || '';
  }

  function packTips(hi, lo, rainMm, rainNote) {
    var tips = [];
    if (hi >= 30) tips.push('Light breathable layers', 'Sunscreen', 'Hat / shade');
    else if (hi >= 22) tips.push('Light layers', 'Comfortable daywear');
    else if (hi >= 15) tips.push('Light jacket or cardigan', 'Layers for cool evenings');
    else if (hi >= 8) tips.push('Warm jacket', 'Long pants', 'Closed shoes');
    else tips.push('Coat / insulated layer', 'Warm base layers', 'Gloves if windy');
    if (lo <= 10 && hi >= 18) tips.push('Day–night swing: pack a warmer layer');
    if ((rainMm != null && rainMm >= 80) || (rainNote && /wet|showery/i.test(rainNote))) tips.push('Rain jacket', 'Waterproof shoes');
    else if (rainMm != null && rainMm >= 40) tips.push('Compact umbrella or light rain shell');
    if (hi >= 28 && rainMm != null && rainMm < 40) tips.push('Stay hydrated');
    var seen = {}, out = [];
    tips.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
    return out.slice(0, 6);
  }

  function rainNoteFromMm(mm) {
    if (mm == null) return '';
    if (mm >= 150) return 'Often wet — pack a rain layer';
    if (mm >= 80) return 'Often showery — pack a light rain layer';
    if (mm >= 40) return 'Some rain likely across the month';
    if (mm >= 15) return 'Mostly dry with occasional showers';
    return 'Typically dry';
  }

  function wmoLabel(code) {
    var c = Number(code);
    if (c === 0) return 'Clear';
    if (c === 1) return 'Mainly clear';
    if (c === 2) return 'Partly cloudy';
    if (c === 3) return 'Overcast';
    if (c === 45 || c === 48) return 'Fog';
    if (c >= 51 && c <= 57) return 'Drizzle';
    if (c >= 61 && c <= 67) return 'Rain';
    if (c >= 71 && c <= 77) return 'Snow';
    if (c >= 80 && c <= 82) return 'Showers';
    if (c >= 85 && c <= 86) return 'Snow showers';
    if (c >= 95 && c <= 99) return 'Thunderstorm';
    return 'Mixed';
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

  function hideGeoDrop() {
    geoDrop.hidden = true;
    geoDrop.innerHTML = '';
  }

  function showGeoDrop(results) {
    geoDrop.innerHTML = '';
    if (!results.length) {
      hideGeoDrop();
      return;
    }
    results.forEach(function (r) {
      var li = document.createElement('li');
      li.setAttribute('role', 'option');
      var bits = [r.name];
      if (r.admin1) bits.push(r.admin1);
      if (r.country) bits.push(r.country);
      li.innerHTML = '<button type="button"><b>' + esc(r.name) + '</b><span>' +
        esc([r.admin1, r.country].filter(Boolean).join(', ')) + '</span></button>';
      li.querySelector('button').addEventListener('click', function () {
        hideGeoDrop();
        pickGeocoded(r);
      });
      geoDrop.appendChild(li);
    });
    geoDrop.hidden = false;
  }

  function renderClimate(place, m, monthName) {
    if (m) {
      climateText.innerHTML =
        'In <b>' + esc(monthName) + '</b>, ' + esc(place.name) + ' is typically around ' +
        '<b>' + esc(m.typical_high_c) + '°</b> high / <b>' + esc(m.typical_low_c) + '°</b> low' +
        (m.typical_precip_mm != null ? ', with about <b>' + esc(m.typical_precip_mm) + ' mm</b> of rain for the month' : '') +
        '. ' + esc(m.rain_note || '') +
        '<br><small style="color:var(--muted)">Based on 2015–2019 monthly averages (Open-Meteo / ERA5). This is climate, not a prediction for a specific day.</small>';
      packList.innerHTML = packTips(m.typical_high_c, m.typical_low_c, m.typical_precip_mm, m.rain_note)
        .map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('');
    } else {
      climateText.textContent = 'Couldn’t load climate for this place — use the near-term strip above.';
      packList.innerHTML = '';
    }
  }

  function showSeeded(city) {
    activePlace = { kind: 'seeded', id: city.id, name: city.name, country: city.country, lat: city.lat, lon: city.lon, city: city };
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
    renderClimate(city, m, monthName);
    planSrc.textContent =
      'Outlook: MET Norway (seeded city) · Climate: Open-Meteo archive · Places: Open-Meteo Geocoding · Made possible by Weather Bot';
    document.querySelectorAll('.suggest button').forEach(function (b) {
      b.classList.toggle('is-on', b.dataset.id === city.id);
    });
    q.value = city.name;
    setStatus('');
  }

  function cacheKey(lat, lon) {
    return Number(lat).toFixed(2) + ',' + Number(lon).toFixed(2);
  }

  function fetchOpenMeteoOutlook(lat, lon) {
    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + encodeURIComponent(lat) +
      '&longitude=' + encodeURIComponent(lon) +
      '&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum' +
      '&current_weather=true&timezone=auto&forecast_days=16';
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('Outlook request failed');
      return r.json();
    }).then(function (data) {
      var daily = data.daily || {};
      var times = daily.time || [];
      var days = times.map(function (date, i) {
        var hi = daily.temperature_2m_max[i];
        var lo = daily.temperature_2m_min[i];
        var precip = daily.precipitation_sum[i];
        var code = daily.weathercode[i];
        return {
          date: date,
          high_c: hi != null ? Math.round(hi) : '—',
          low_c: lo != null ? Math.round(lo) : '—',
          condition: wmoLabel(code),
          precip_mm: precip != null ? Math.round(precip * 10) / 10 : null,
        };
      });
      var cw = data.current_weather || {};
      return {
        days: days,
        temp_c: cw.temperature != null ? Math.round(cw.temperature) : null,
        condition: cw.weathercode != null ? wmoLabel(cw.weathercode) : '',
        today: days[0] || null,
        tz: data.timezone || '',
      };
    });
  }

  function aggregateClimate(daily) {
    var times = daily.time || [];
    var his = daily.temperature_2m_max || [];
    var los = daily.temperature_2m_min || [];
    var ps = daily.precipitation_sum || [];
    var byMonth = {};
    var precipByYM = {};
    for (var i = 0; i < times.length; i++) {
      if (his[i] == null || los[i] == null) continue;
      var day = times[i];
      var mo = String(Number(day.slice(5, 7)));
      var ym = day.slice(0, 7);
      if (!byMonth[mo]) byMonth[mo] = { hi: [], lo: [] };
      byMonth[mo].hi.push(his[i]);
      byMonth[mo].lo.push(los[i]);
      precipByYM[ym] = (precipByYM[ym] || 0) + (ps[i] || 0);
    }
    var months = {};
    Object.keys(byMonth).forEach(function (mo) {
      var hiArr = byMonth[mo].hi;
      var loArr = byMonth[mo].lo;
      var mean = function (arr) {
        var s = 0;
        for (var j = 0; j < arr.length; j++) s += arr[j];
        return s / arr.length;
      };
      var precipMonths = [];
      Object.keys(precipByYM).forEach(function (ym) {
        if (String(Number(ym.slice(5, 7))) === mo) precipMonths.push(precipByYM[ym]);
      });
      var precipMean = precipMonths.length ? mean(precipMonths) : null;
      var hi = Math.round(mean(hiArr) * 10) / 10;
      var lo = Math.round(mean(loArr) * 10) / 10;
      var precip = precipMean != null ? Math.round(precipMean) : null;
      months[mo] = {
        typical_high_c: Math.round(hi),
        typical_low_c: Math.round(lo),
        typical_precip_mm: precip,
        rain_note: rainNoteFromMm(precip),
      };
    });
    return { months: months };
  }

  function fetchClimateNormals(lat, lon) {
    var key = cacheKey(lat, lon);
    if (climateCache[key]) return Promise.resolve(climateCache[key]);
    var url = 'https://archive-api.open-meteo.com/v1/archive?latitude=' + encodeURIComponent(lat) +
      '&longitude=' + encodeURIComponent(lon) +
      '&start_date=2015-01-01&end_date=2019-12-31' +
      '&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=GMT';
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('Climate request failed');
      return r.json();
    }).then(function (data) {
      var agg = aggregateClimate(data.daily || {});
      climateCache[key] = agg;
      return agg;
    });
  }

  function applyOutlookAndClimate(place, outlookData, climMonths) {
    activePlace = place;
    result.classList.add('is-on');
    resTitle.textContent = place.name;
    var locBits = [place.admin1, place.country].filter(Boolean);
    document.getElementById('res-eyebrow').textContent = locBits.join(', ') || 'Outlook';
    var t = outlookData.today || {};
    resNow.textContent =
      (outlookData.temp_c != null ? 'Now about ' + outlookData.temp_c + '°C · ' : '') +
      (outlookData.condition || '') +
      (t.high_c != null ? ' · Today ' + t.high_c + '° / ' + t.low_c + '°' : '');
    var days = (outlookData.days || []).slice(0, 16);
    outlook.innerHTML = days.map(dayCard).join('');
    outlook.style.gridTemplateColumns = 'repeat(' + Math.min(8, Math.max(4, days.length)) + ',minmax(0,1fr))';

    var mo = monthEl.value;
    var m = climMonths && climMonths.months && climMonths.months[mo];
    var monthName = monthEl.options[monthEl.selectedIndex].text;
    renderClimate(place, m, monthName);
    planSrc.textContent =
      'Outlook: Open-Meteo forecast · Climate: Open-Meteo archive (ERA5, 2015–2019) · Places: Open-Meteo Geocoding · Made possible by Weather Bot';
    document.querySelectorAll('.suggest button').forEach(function (b) { b.classList.remove('is-on'); });
    q.value = place.name;
    setStatus('');
  }

  function pickGeocoded(r) {
    var place = {
      kind: 'geo',
      id: 'geo-' + r.id,
      name: r.name,
      country: r.country || '',
      admin1: r.admin1 || '',
      lat: r.latitude,
      lon: r.longitude,
    };
    setStatus('Looking up weather for ' + r.name + '…');
    result.classList.add('is-on');
    resTitle.textContent = r.name;
    resNow.textContent = 'Loading outlook and climate…';
    outlook.innerHTML = '';
    climateText.textContent = '';
    packList.innerHTML = '';

    Promise.all([
      fetchOpenMeteoOutlook(place.lat, place.lon),
      fetchClimateNormals(place.lat, place.lon).catch(function () { return null; }),
    ]).then(function (pair) {
      applyOutlookAndClimate(place, pair[0], pair[1]);
    }).catch(function (err) {
      setStatus('Couldn’t load weather for that place. Try again.');
      resNow.textContent = err.message || 'Request failed';
    });
  }

  function geocode(name) {
    var url = 'https://geocoding-api.open-meteo.com/v1/search?name=' +
      encodeURIComponent(name) + '&count=5&language=en&format=json';
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('Place lookup failed');
      return r.json();
    }).then(function (data) {
      return data.results || [];
    });
  }

  function resolveQuery(query) {
    var seeded = findCity(query);
    if (seeded) {
      hideGeoDrop();
      showSeeded(seeded);
      return;
    }
    var qtrim = (query || '').trim();
    if (!qtrim) {
      setStatus('Type a city name to search.');
      return;
    }
    setStatus('Looking up “' + qtrim + '”…');
    hideGeoDrop();
    geocode(qtrim).then(function (results) {
      // Prefer populated places over airports when names collide
      var filtered = results.filter(function (r) {
        return !r.feature_code || r.feature_code.indexOf('AIR') !== 0;
      });
      if (!filtered.length) filtered = results;
      if (!filtered.length) {
        setStatus('Couldn’t find that place. Try another spelling or a nearby city.');
        result.classList.add('is-on');
        resTitle.textContent = 'Not found';
        resNow.textContent = 'No match for “' + qtrim + '”.';
        outlook.innerHTML = '';
        return;
      }
      if (filtered.length === 1) {
        pickGeocoded(filtered[0]);
        return;
      }
      setStatus('Pick a place:');
      showGeoDrop(filtered);
    }).catch(function () {
      setStatus('Couldn’t look up that place. Check your connection and try again.');
    });
  }

  function wireSuggest(cities) {
    suggest.innerHTML = '';
    cities.slice(0, 12).forEach(function (c) {
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.id = c.id;
      b.textContent = c.name;
      b.addEventListener('click', function () {
        hideGeoDrop();
        showSeeded(c);
      });
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
    var startQ = params.get('city') || 'Hong Kong';
    if (params.get('month')) monthEl.value = params.get('month');
    resolveQuery(startQ);
  }).catch(function (err) {
    suggest.innerHTML = '<li style="color:var(--rust)">Could not load data: ' + esc(err.message) + '</li>';
  });

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    resolveQuery(q.value);
  });

  monthEl.addEventListener('change', function () {
    if (!activePlace) return;
    if (activePlace.kind === 'seeded') {
      showSeeded(activePlace.city);
      return;
    }
    // geocoded: re-render climate from cache (or fetch)
    setStatus('Updating climate for ' + monthEl.options[monthEl.selectedIndex].text + '…');
    fetchClimateNormals(activePlace.lat, activePlace.lon).then(function (clim) {
      var mo = monthEl.value;
      var m = clim && clim.months && clim.months[mo];
      renderClimate(activePlace, m, monthEl.options[monthEl.selectedIndex].text);
      setStatus('');
    }).catch(function () {
      setStatus('Couldn’t update climate for that month.');
    });
  });

  document.addEventListener('click', function (ev) {
    if (!geoDrop.hidden && !geoDrop.contains(ev.target) && ev.target !== q) hideGeoDrop();
  });
})();
