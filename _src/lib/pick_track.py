#!/usr/bin/env python3
"""Pick today's Temple Street soundtrack from the HKO data JSON.

    python3 pick_track.py data-$D.json                 # pick + log (music-picks.log)
    python3 pick_track.py data-$D.json --dry-run       # pick, don't log
    python3 pick_track.py data-$D.json --path-only     # print only the audio path (for shell use)
    options: --hour H (time of day override), --date YYYY-MM-DD, --avoid-days 10,
             --log FILE, --tags catalogue-tags.json, --repick (ignore today's logged pick), --json

Rules
- Conditions -> one primary vibe (+ fallback vibes), in priority order:
  typhoon signal >= 8 (catalogue gap -> indoor shelter tracks) > black/red/amber rainstorm or heavy-rain icon
  > thunderstorm (WTS / icon 65 / forecast text) > rain / showers (icons 53,54,62,63, rain chance >= 70%)
  > cold (WCOLD/WFROST, icon 93, low <= 12, high <= 16) > cool (icon 92, high <= 22)
  > very hot (WHOT, icon 90, high >= 33) > fog/mist/haze or humidity >= 90 > windy (TC3, WMSGNL, icon 80, force >= 6)
  > cloudy (60, 61, 76) > sunny/fine. Evening/night (hour >= 19 or < 5) switches fine/cloudy days to the night vibe.
- Candidates: tracks tagged with the vibe (primary tag weight 3, secondary 1, Planogram hero +1).
  Winter-only tracks (winter_only in the catalogue: 06, 35, 40 Mint, 50, 59) are allowed only on cold days (06 Christmas Vlog
  only 1 Dec - 6 Jan). do_not_autoplay tracks (60 Observations, vocal) are never picked.
- MP3 is the source (catalogue is MP3-only since 27 Sep 2026); log lines match by file stem, so old .wav lines still count.
- No repeats: tracks (and other versions of the same song, catalogue version_group) logged in the last --avoid-days days (other dates) are excluded while alternatives
  remain; fallback vibes are added if the pool gets too small.
- Deterministic: the RNG is seeded from the date + vibe, so a rerun for the same date gives the same track
  (the date's own log line is replaced, not duplicated).
"""
import argparse, datetime as dt, hashlib, json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAGS = '/workspace/music/temple-street/catalogue-tags.json'
LOG = os.path.join(HERE, 'music-picks.log')
SHELTER = [32, 2, 39, 22, 37]      # typhoon fallback (no real typhoon track in the catalogue)

FALLBACK = {
    'sunny_bright': ['very_hot_lazy', 'cloudy_mellow'],
    'very_hot_lazy': ['sunny_bright', 'humid_misty'],
    'cloudy_mellow': ['humid_misty', 'light_rain'],
    'humid_misty': ['cloudy_mellow', 'very_hot_lazy'],
    'light_rain': ['cloudy_mellow', 'heavy_rain'],
    'heavy_rain': ['light_rain', 'thunderstorm_moody'],
    'thunderstorm_moody': ['heavy_rain', 'evening_night_fine'],
    'windy_typhoon': ['cool_cold_dry', 'sunny_bright'],
    'cool_cold_dry': ['cloudy_mellow', 'evening_night_fine'],
    'evening_night_fine': ['cool_cold_dry', 'cloudy_mellow'],
    'typhoon_shelter': ['heavy_rain', 'thunderstorm_moody'],
}


def classify(d, hour=None):
    """Return (vibe, cold_ok, reasons[])."""
    cur, today = d.get('current') or {}, d.get('today') or {}
    warns = d.get('warnings') or []
    codes = {(w.get('code') or '').upper() for w in warns} | {(w.get('key') or '').upper() for w in warns}
    icons = {c for c in (cur.get('weather_code'), today.get('weather_code')) if c}
    day_icons = {h.get('weather_code') for h in d.get('hourly') or [] if h.get('weather_code') and 7 <= (h.get('hour') or 0) <= 18}
    text = ' '.join(str(today.get(k) or '') for k in ('summary', 'local_forecast')).lower()
    hi, lo, hum = today.get('high'), today.get('low'), cur.get('humidity')
    try:
        rain_pct = int(re.sub(r'\D', '', str(today.get('chance_of_rain') or '')) or -1)
    except ValueError:
        rain_pct = -1
    wind = (today.get('wind_raw') or today.get('wind') or '').lower()
    forces = [int(x) for x in re.findall(r'\d+', wind)]
    fmax = max(forces) if forces else 0
    tc = max([int(re.sub(r'\D', '', c) or 0) for c in codes if re.match(r'TC\d', c)] or [0])
    if hour is None:
        try:
            hour = int((d.get('generated_at') or '')[11:13])
        except ValueError:
            hour = dt.datetime.now().hour
    month = int((d.get('date') or dt.date.today().isoformat())[5:7])
    why = []
    has = lambda *ws: any(w in text for w in ws)

    cold = bool({'WCOLD', 'WFROST'} & codes) or 93 in icons or (lo is not None and lo <= 12) or (hi is not None and hi <= 16)
    cool = cold or 92 in icons or (hi is not None and hi <= 22) or (month in (11, 12, 1, 2, 3) and has('cool', 'cold'))
    rainstorm = next((c for c in codes if c in ('WRAINA', 'WRAINR', 'WRAINB')), None)
    heavy = rainstorm or 64 in icons or has('heavy rain', 'heavy showers', 'squally', 'rainstorm')
    thunder = 'WTS' in codes or 65 in icons or has('thunderstorm')
    rain = bool(icons & {53, 54, 62, 63}) or rain_pct >= 70 or (has('rain', 'showers') and not has('no rain') and (rain_pct < 0 or rain_pct >= 40))
    hot = 'WHOT' in codes or 90 in icons or (hi is not None and hi >= 33)
    misty = bool(icons & {83, 84, 85}) or (hum is not None and hum >= 90) or has('fog', 'mist', 'haz')
    windy = tc >= 3 or 'WMSGNL' in codes or 80 in icons or fmax >= 6 or has('strong winds', 'gale', 'gusty')
    cloudy = bool(icons & {60, 61, 76}) or (has('cloudy', 'overcast') and not has('mainly fine', 'sunny'))
    night = hour >= 19 or hour < 5

    if tc >= 8:
        why.append(f'Typhoon signal No.{tc} -> catalogue has no typhoon track; using indoor-shelter tracks')
        vibe = 'typhoon_shelter'
    elif heavy:
        why.append(f"heavy rain ({rainstorm or 'icon/forecast text'})" + (' with thunder' if thunder else ''))
        vibe = 'heavy_rain'
    elif thunder:
        why.append('thunderstorm (' + ('WTS warning' if 'WTS' in codes else 'icon 65/forecast text') + ')')
        vibe = 'thunderstorm_moody'
    elif rain:
        why.append(f'rain/showers (icons {sorted(icons)}, chance of rain {rain_pct}%)')
        vibe = 'light_rain'
    elif cool:
        why.append('cold day' if cold else 'cool day' + f' (high {hi}, low {lo})')
        vibe = 'cool_cold_dry'
    elif hot:
        why.append('very hot (' + ', '.join(x for x in ['WHOT warning' if 'WHOT' in codes else '', 'icon 90' if 90 in icons else '',
                                                        f'high {hi}°' if hi is not None and hi >= 33 else ''] if x) + ')')
        vibe = 'very_hot_lazy'
    elif misty:
        why.append(f'humid/misty (humidity {hum}%, icons {sorted(icons)})')
        vibe = 'humid_misty'
    elif windy:
        why.append(f'windy (TC{tc or "-"}, force {fmax or "-"})')
        vibe = 'windy_typhoon'
    elif cloudy:
        why.append(f'cloudy (icons {sorted(icons)})')
        vibe = 'cloudy_mellow'
    else:
        why.append(f'sunny/fine (icons {sorted(icons) or "-"}, high {hi})')
        vibe = 'sunny_bright'
    if night and vibe in ('sunny_bright', 'cloudy_mellow', 'very_hot_lazy', 'humid_misty'):
        why.append(f'evening/night ({hour:02d}:00) -> night vibe')
        vibe = 'evening_night_fine'
    ctx = dict(cold=cold, dec=(month == 12 or (month == 1 and int((d.get("date") or "2000-01-01")[8:10]) <= 6)),
               hot=hot, humid=misty, windy=windy, hour=hour, icons=sorted(icons), day_icons=sorted(day_icons))
    return vibe, ctx, why


def stem(f):
    """'21-halo-halo-akistudy.wav' / '.mp3' -> '21-halo-halo-akistudy' (log/catalogue match ignores the extension)."""
    return os.path.splitext(os.path.basename(f or ''))[0]


def read_log(path):
    out = []
    if os.path.exists(path):
        for line in open(path):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 3 and re.match(r'\d{4}-\d\d-\d\d', p[0]):
                out.append(p)
    return out


def pick(d, tags, log_rows, date, hour=None, avoid_days=10, repick=False):
    vibe, ctx, why = classify(d, hour)
    tracks = tags['tracks']
    by_sku = {t['sku']: t for t in tracks}
    song = lambda t: t.get('version_group') or stem(t['file'])      # versions of one song count as one for no-repeats
    stem_song = {stem(t['file']): song(t) for t in tracks}
    D = dt.date.fromisoformat(date)
    recent = {}
    for p in log_rows:
        ld = dt.date.fromisoformat(p[0])
        if ld != D and 0 < (D - ld).days <= avoid_days or (repick and ld == D):
            recent[stem_song.get(stem(p[1]), stem(p[1]))] = p[0]   # by stem (old log lines say .wav) -> song/version group

    def eligible(t):
        if t.get('do_not_autoplay'):        # e.g. 60 Observations (vocal)
            return False
        if t['winter_only']:
            return ctx['cold'] and (t['season'] != 'dec' or ctx['dec'])
        return True

    def pool_for(v):
        if v == 'typhoon_shelter':
            return {s: 4 - i * 0.5 for i, s in enumerate(SHELTER)}
        w = {}
        for t in tracks:
            if v in t['vibes'] and eligible(t):
                w[t['sku']] = (3 if t['vibes'][0] == v else 1) + (1 if t['planogram_hero_for'] else 0)
                # nudge by audio: hot/lazy prefers low energy, sunny prefers bright, storms prefer dark
                if v == 'very_hot_lazy': w[t['sku']] += 1 - t['energy']
                if v == 'sunny_bright': w[t['sku']] += t['brightness']
                if v in ('thunderstorm_moody', 'heavy_rain'): w[t['sku']] += 1 - t['brightness']
        return w

    pool = pool_for(vibe)
    fresh = {s: w for s, w in pool.items() if song(by_sku[s]) not in recent}
    used_fb = []
    for fb in FALLBACK.get(vibe, []):
        if len(fresh) >= 2:
            break
        extra = {s: w * 0.5 for s, w in pool_for(fb).items() if s not in pool and song(by_sku[s]) not in recent}
        if extra:
            used_fb.append(fb); fresh.update(extra)
    if not fresh:                       # everything used recently: allow the least recently used from the pool
        fresh = dict(pool)
        why.append('all matching tracks used in the last %d days; allowing repeats' % avoid_days)
    seed = int(hashlib.sha256(f'{date}|{vibe}'.encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    skus = sorted(fresh)
    choice = rng.choices(skus, weights=[fresh[s] for s in skus], k=1)[0]
    t = by_sku[choice]
    excluded = sorted({by_sku[s]['sku'] for s in pool if song(by_sku[s]) in recent})
    if excluded:
        why.append('skipped recently used: ' + ', '.join(f'{s:02d}' for s in excluded))
    if used_fb:
        why.append('pool topped up from: ' + ', '.join(used_fb))
    return dict(date=date, vibe=vibe, sku=t['sku'], title=t['title'], display_title=t.get('display_title') or t['title'],
                display_title_unverified=bool(t.get('display_title_unverified')), file=t['file'],
                path=os.path.join(tags['meta']['dir'], t['file']), start_s=t['start_s'],
                track_vibes=t['vibes'], track_reason=t['reason'], why=why,
                candidates=[f"{s:02d} {by_sku[s]['title']} (w={fresh[s]:.1f})" for s in skus], ctx=ctx)


def write_log(path, res, src):
    rows = [p for p in read_log(path) if p[0] != res['date']]
    rows.append([res['date'], res['file'], res['vibe'], res['title'], os.path.basename(src),
                 dt.datetime.now().strftime('%Y-%m-%dT%H:%M%z') or dt.datetime.now().isoformat(timespec='minutes')])
    rows.sort(key=lambda p: p[0])
    with open(path, 'w') as f:
        f.write('# date\tfile\tvibe\ttitle\tdata_json\tpicked_at (HKT)\n')
        for p in rows:
            f.write('\t'.join(p) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('data')
    ap.add_argument('--tags', default=TAGS)
    ap.add_argument('--log', default=LOG)
    ap.add_argument('--date')
    ap.add_argument('--hour', type=int)
    ap.add_argument('--avoid-days', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true', help="don't write the log")
    ap.add_argument('--repick', action='store_true', help="also exclude the track already logged for this date")
    ap.add_argument('--path-only', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    d = json.load(open(a.data))
    tags = json.load(open(a.tags))
    date = a.date or d.get('date') or dt.date.today().isoformat()
    res = pick(d, tags, read_log(a.log), date, a.hour, a.avoid_days, a.repick)
    if not a.dry_run:
        write_log(a.log, res, a.data)
    if a.path_only:
        print(res['path']); return
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False)); return
    print(f"{date}: vibe = {res['vibe']}")
    print(f"  track : {res['sku']:02d} {res['title']}  ->  {res['path']}  (start {res['start_s']:.1f}s)")
    print(f"  public: {res['display_title']}" + ('  (UNVERIFIED: no Spotify release found)' if res['display_title_unverified'] else '  (official Spotify title)'))
    print(f"  why   : {'; '.join(res['why'])}")
    print(f"  track tags: {', '.join(res['track_vibes'])}. {res['track_reason']}")
    print(f"  pool  : {', '.join(res['candidates'])}")
    print('  log   : ' + ('(dry run, not logged)' if a.dry_run else a.log))
    print(res['path'])


if __name__ == '__main__':
    main()
