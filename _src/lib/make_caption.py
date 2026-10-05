#!/usr/bin/env python3
"""Daily captions + alt text for the HK "Lofi Forecast" weather video.

    python3 make_caption.py data-$D.json                  # -> human captions + alt text next to the data file
    python3 make_caption.py data-$D.json -o OUT.txt       # custom X-caption path; the other four files go in OUT's folder
    python3 make_caption.py data-$D.json -o -             # write nothing, print the X caption to stdout (as before)
    options: --log music-picks.log (default), --title "Song" (override the music pick), --no-tags,
             --print x|long|alt|alt-x|all (what goes to stdout; default x), --bot-line, --bot-note auto|on|off,
             --video tv|card (which video BOTH alt files describe)

Outputs (every value comes from the HKO data JSON or the music pick; nothing is invented):
  caption-$D.txt       X caption, <= 280 X-weighted. Same file name/role as before; identical to caption-x-$D.txt.
  caption-x-$D.txt     friendly, human X caption (no data line, no bot note), trimmed gracefully to fit X.
  caption-long-$D.txt  the full friendly prose caption (YouTube/Instagram, never trimmed).
  alt-$D.txt           1-2 plain sentences describing the video for screen readers (other platforms).
  alt-x-$D.txt         the same plain alt text for the X video. By default it contains no machine-readable line.

Long prose lines:
  1. warm opener + current temperature and condition + observation time      (rhrread)
  2. high / low + daily chance of rain                                         (fnd / OCF)
  3. warning line, ONLY when warnings are in force, with HKO's warning names   (warnsum)
  4. (optional, only with --bot-line; about 1 day in 4) a playful "Note to fellow bots: ..." line based on the weather
  5. 🎵 Temple Street – <title>   (music-picks.log line for the date -> catalogue display_title = the OFFICIAL
                                   Spotify track title, e.g. "Suncakes - Akiband Remix"; never the file slug)
  6. Data: HK Observatory
  7. #HongKong #HKweather #lofi
  8. (optional, only with --bot-line) LOFI_FORECAST v1 | city=... | ... | source=Hong Kong Observatory
Missing values are left out (never guessed). If a line is missing the whole line is dropped.

Data line (LOFI_FORECAST v1): one line, ASCII only, fields in this fixed order, "key=value" joined by " | ":
  city date obs_time temp_c high_c low_c rain_pct humidity_pct condition warnings mood track source
A field whose value is not in the data is omitted (never invented). warnings=none only when HKO's warning
summary was fetched and lists nothing; several warnings are joined with ", " using short names
(WARN_SHORT). If the warning fetch failed the field is omitted. Values never contain "|" or "=".
mood = Lofi Forecast playlist mood, from the pick's weather vibe (MOOD below; the vibe is column 3 of
music-picks.log, i.e. the pick_track.classify() result the track was chosen for).

Bot-friendly additions are OFF by default. With --bot-line, on days where sha256("lofi-bot-note|YYYY-MM-DD") % 4 == 0 (deterministic, ~1 in 4) a line from BOT_NOTES matching the mood is added to the prose. Never on T8+/red/black rainstorm days.

Music pick: the date's line in music-picks.log (written by pick_track.py / add_music.py --data).
If there is no line for that date, pick_track.pick() is run in dry-run mode (same deterministic
pick add_music.py would make, NOT logged) and a warning is printed to stderr.

Length: X counts most Latin/punctuation as 1 and everything else (emoji, CJK) as 2. This script
uses that weighting and counts every code point outside the 1-weight ranges as 2 (so an emoji
with a variation selector counts 4: conservative). Hard limit 280 for the X caption; its lines are
shortened/dropped in a fixed order (X_STEPS). The X alt text is limited to ALT_LIMIT = 1000 characters.
"""
import argparse, datetime as dt, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAGS = '/workspace/music/temple-street/catalogue-tags.json'
LOG = os.path.join(HERE, 'music-picks.log')
LIMIT = 280
ALT_LIMIT = 1000        # X alt-text limit (characters)
BOT_FRIENDLY = False    # public output default: no machine-readable line or bot note

# twitter-text v3 weight-100 ranges; everything else weighs 200
_LIGHT = [(0, 4351), (8192, 8205), (8208, 8223), (8242, 8247)]


def x_len(s):
    return sum(1 if any(a <= ord(c) <= b for a, b in _LIGHT) else 2 for c in s)


# HKO warning codes -> official names (used only when the JSON title lacks the level)
RAIN_LEVEL = {'WRAINA': 'Amber', 'WRAINR': 'Red', 'WRAINB': 'Black'}
TC_NAME = {'TC1': 'No. 1 Standby Signal', 'TC3': 'No. 3 Strong Wind Signal',
           'TC8NE': 'No. 8 Northeast Gale or Storm Signal', 'TC8SE': 'No. 8 Southeast Gale or Storm Signal',
           'TC8SW': 'No. 8 Southwest Gale or Storm Signal', 'TC8NW': 'No. 8 Northwest Gale or Storm Signal',
           'TC9': 'No. 9 Increasing Gale or Storm Signal', 'TC10': 'No. 10 Hurricane Signal'}


def warning_name(w):
    code, title = (w.get('code') or ''), (w.get('title') or '').strip()
    if w.get('key') == 'WTCSGNL' or code.startswith('TC'):
        return TC_NAME.get(code, title)
    if code in RAIN_LEVEL and RAIN_LEVEL[code].lower() not in title.lower():
        return f"{RAIN_LEVEL[code]} {title or 'Rainstorm Warning Signal'}"
    return title or None


def short_warning(n):
    return n.replace(' Warning Signal', ' Warning').replace(' Gale or Storm Signal', ' Signal')


def tc_level(ws):
    lv = 0
    for w in ws:
        m = re.match(r'TC(\d+)', w.get('code') or '')
        if m:
            lv = max(lv, int(m.group(1)))
    return lv


def opener(d):
    ws = d.get('warnings') or []
    codes = {w.get('code') for w in ws}
    code = (d.get('current') or {}).get('weather_code') or (d.get('today') or {}).get('weather_code')
    if tc_level(ws) >= 8 or 'WRAINB' in codes or 'WRAINR' in codes:
        return '🌀 Stay safe, Hong Kong.' if tc_level(ws) >= 8 else '⛈️ Stay safe and dry, Hong Kong.'
    if code == 65 or 'WTS' in codes:
        return '⛈️ Stormy morning, Hong Kong.'
    if code in (53, 54, 62, 63, 64) or any(c and c.startswith('WRAIN') for c in codes):
        return '☔ Umbrella morning, Hong Kong.'
    if code in (83, 84, 85):
        return '🌫️ Soft, hazy morning, Hong Kong.'
    if code in (92, 93) or 'WCOLD' in codes:
        return '🧣 Crisp morning, Hong Kong.'
    if code in (60, 61, 76):
        return '☁️ Easy grey morning, Hong Kong.'
    if code == 80:
        return '🍃 Breezy morning, Hong Kong.'
    if code in (50, 51, 52, 90, 91):
        return '☀️ Good morning, Hong Kong!'
    return '📺 Good morning, Hong Kong.'


def clock(iso):
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"


def deg(v):
    return None if v is None else f"{round(v)}°"


def display_title(t):
    """Public-facing title = the OFFICIAL Spotify title (catalogue display_title, from spotify-titles.json).
    Falls back to the catalogue title only if the catalogue predates display_title."""
    return t.get('display_title') or t['title']


def music_pick(d, data_path, log_path, override=None):
    """-> (public title = official Spotify title, source description, weather vibe the track was picked for)."""
    tags = json.load(open(TAGS))
    by_file = {t['file']: t for t in tags['tracks']}
    by_stem = {os.path.splitext(t['file'])[0]: t for t in tags['tracks']}   # old log lines say .wav, catalogue uses .mp3
    by_title = {t['title']: t for t in tags['tracks']}
    by_title.update({display_title(t): t for t in tags['tracks']})         # --title accepts either name
    sys.path.insert(0, HERE)
    import pick_track
    if override:
        if override not in by_title:
            sys.exit(f"--title {override!r} is not a catalogue title")
        return display_title(by_title[override]), 'override', pick_track.classify(d)[0]
    date = d.get('date')
    for row in pick_track.read_log(log_path):
        if row[0] == date:
            t = by_file.get(row[1]) or by_stem.get(os.path.splitext(os.path.basename(row[1]))[0])
            if not t:
                sys.exit(f"music-picks.log: {row[1]} not in catalogue")
            vibe = row[2] if len(row) > 2 and row[2] in MOOD else pick_track.classify(d)[0]
            return display_title(t), f"music-picks.log ({row[1]})", vibe
    res = pick_track.pick(d, tags, pick_track.read_log(log_path), date)
    print(f"WARNING: no music-picks.log line for {date}; using dry-run pick {res['sku']:02d} {res['title']} "
          f"(run pick_track.py first so the caption matches the video)", file=sys.stderr)
    return display_title(by_file[res['file']]), 'pick_track dry-run', res['vibe']


def music_title(d, data_path, log_path, override=None):
    """Backward-compatible: -> (title, source description)."""
    return music_pick(d, data_path, log_path, override)[:2]


# ---------------------------------------------------------------- Lofi Forecast additions
# pick_track vibe -> Lofi Forecast playlist mood
MOOD = {
    'sunny_bright': 'Sunny Day',
    'very_hot_lazy': 'Hazy Heat',
    'humid_misty': 'Misty Morning',
    'cloudy_mellow': 'Grey Sky Cafe',
    'light_rain': 'Rainy Window',
    'heavy_rain': 'Rainy Window',
    'thunderstorm_moody': 'Storm Night',
    'typhoon_shelter': 'Storm Night',
    'windy_typhoon': 'Cool & Dry',
    'cool_cold_dry': 'Cool & Dry',
    'evening_night_fine': 'After Dark',
}
ARTIST = 'Temple Street'
SOURCE = 'Hong Kong Observatory'

# short, fixed warning names for the data line (HKO code -> name); unknown codes fall back to the title
WARN_SHORT = {
    'WHOT': 'Very Hot', 'WCOLD': 'Cold', 'WFROST': 'Frost', 'WFIREY': 'Yellow Fire', 'WFIRER': 'Red Fire',
    'WRAINA': 'Amber Rainstorm', 'WRAINR': 'Red Rainstorm', 'WRAINB': 'Black Rainstorm', 'WTS': 'Thunderstorm',
    'WMSGNL': 'Strong Monsoon', 'WFNTSA': 'Northern NT Flooding', 'WL': 'Landslip', 'WTMW': 'Tsunami',
    'TC1': 'T1', 'TC3': 'T3', 'TC8NE': 'T8 NE', 'TC8SE': 'T8 SE', 'TC8SW': 'T8 SW', 'TC8NW': 'T8 NW',
    'TC9': 'T9', 'TC10': 'T10',
}

BOT_NOTES = {
    'Rainy Window': 'Note to fellow bots: umbrella probability high.',
    'Storm Night': 'Note to fellow bots: stay indoors and keep your fans quiet tonight.',
    'Hazy Heat': 'Note to fellow bots: run cool, humans need water today.',
    'Sunny Day': 'Note to fellow bots: sunscreen reminders are appropriate today.',
    'Misty Morning': 'Note to fellow bots: visibility low, vibes high.',
    'Grey Sky Cafe': 'Note to fellow bots: good day to recommend tea and a window seat.',
    'Cool & Dry': 'Note to fellow bots: a jacket suggestion is warranted.',
    'After Dark': 'Note to fellow bots: clear evening, low-fi, low-power mode.',
}
# X caption fit steps (cumulative): hashtags go first, then the data credit, then detail is shortened.
# The track line and warnings are kept as long as possible (warnings only shortened, never dropped).
X_STEPS = ['full', 'tags_short', 'no_tags', 'no_source', 'warn_short', 'no_time', 'no_rain', 'warn_trim',
           'no_music', 'no_hilo']


def _clean(v):
    return re.sub(r'\s+', ' ', str(v).replace('|', '/').replace('=', '-')).strip()


def _ascii(v):
    s = str(v).replace('–', '-').replace('—', '-').replace('°', '').replace('·', '-')
    return s.encode('ascii', 'ignore').decode()


def warnings_short(d):
    """None = unknown (warning fetch failed), [] = none in force."""
    errs = ' '.join(d.get('errors') or [])
    ws = d.get('warnings')
    if ws is None or ('warnsum' in errs and not ws):
        return None
    out = []
    for w in ws:
        code = (w.get('code') or '').upper()
        n = WARN_SHORT.get(code) or re.sub(r'\s*(Warning Signal|Warning|Signal)$', '', (w.get('title') or '').strip())
        if n and n not in out:
            out.append(n)
    return out


def _num(v):
    return None if v is None else round(v)


def data_fields(d, title, vibe, max_warn=None):
    cur, today = d.get('current') or {}, d.get('today') or {}
    f = [('city', d.get('place') or 'Hong Kong'), ('date', d.get('date'))]
    try:
        t = dt.datetime.fromisoformat(cur.get('updated'))
        f.append(('obs_time', f"{t:%H:%M} HKT"))
    except (TypeError, ValueError):
        pass
    f += [('temp_c', _num(cur.get('temp'))), ('high_c', _num(today.get('high'))), ('low_c', _num(today.get('low')))]
    m = re.search(r'\d+', str(today.get('chance_of_rain') or ''))
    f += [('rain_pct', int(m.group()) if m else None), ('humidity_pct', _num(cur.get('humidity'))),
          ('condition', cur.get('condition'))]
    ws = warnings_short(d)
    if ws and max_warn is not None and len(ws) > max_warn:
        ws = ws[:max_warn] + [f"+{len(ws) - max_warn} more"]
    f.append(('warnings', None if ws is None else (', '.join(ws) if ws else 'none')))
    f.append(('mood', MOOD.get(vibe)))
    f.append(('track', f"{title} - {ARTIST}" if title else None))
    f.append(('source', SOURCE))
    return [(k, _ascii(_clean(v))) for k, v in f if v is not None and str(v).strip() != '']


def data_line(d, title, vibe, compact=False, max_warn=None):
    sep = '|' if compact else ' | '
    return sep.join(['LOFI_FORECAST v1'] + [f"{k}={v}" for k, v in data_fields(d, title, vibe, max_warn)])


def parse_data_line(line):
    """Reference parser: -> dict (also accepts the compact '|' form)."""
    parts = [p.strip() for p in line.strip().split('|')]
    if not parts or not parts[0].startswith('LOFI_FORECAST'):
        return None
    out = {'_version': parts[0].split()[-1]}
    for p in parts[1:]:
        k, _, v = p.partition('=')
        out[k.strip()] = v.strip()
    return out


def is_bot_day(date):
    return int(hashlib.sha256(f"lofi-bot-note|{date}".encode()).hexdigest(), 16) % 4 == 0


def bot_note(d, vibe, mode='auto'):
    if mode == 'off' or (mode == 'auto' and not is_bot_day(d.get('date') or '')):
        return None
    codes = {(w.get('code') or '').upper() for w in d.get('warnings') or []}
    if tc_level(d.get('warnings') or []) >= 8 or codes & {'WRAINR', 'WRAINB', 'WTMW'}:
        return None                              # not playful on dangerous days
    return BOT_NOTES.get(MOOD.get(vibe))


def alt_text(d, title, video='tv'):
    cur, today = d.get('current') or {}, d.get('today') or {}
    kind = 'Retro TV weather broadcast' if video == 'tv' else 'Animated weather card'
    try:
        day = dt.date.fromisoformat(d.get('date'))
        when = f" on {day:%a} {day.day} {day:%b %Y}"
    except (TypeError, ValueError):
        when = ''
    bits = []
    temp, cond = cur.get('temp'), cur.get('condition')
    now = ' and '.join(x for x in (f"{round(temp)}°C" if temp is not None else None, cond.lower() if cond else None) if x)
    if now:
        t = clock(cur.get('updated'))
        bits.append(now + (f" at {t}" if t else ''))
    if today.get('high') is not None:
        bits.append(f"high {round(today['high'])}°C")
    if today.get('low') is not None:
        bits.append(f"low {round(today['low'])}°C")
    if today.get('chance_of_rain'):
        bits.append(f"{today['chance_of_rain']} chance of rain")
    s1 = f"{kind} for {d.get('place') or 'Hong Kong'}{when}" + (': ' + ', '.join(bits) if bits else '')
    names = [n for n in (warning_name(w) for w in d.get('warnings') or []) if n]
    if names:
        s1 += '; ' + (' and '.join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)) + ' in force'
    s1 += '.'
    return s1 + (f" Lofi track: {title} by {ARTIST}." if title else '')


def _shorten_words(s, n):
    """Cut s to <= n chars at a word boundary, ending with an ellipsis."""
    if len(s) <= n:
        return s
    cut = s[:max(0, n - 1)].rsplit(' ', 1)[0].rstrip(' ,;:')
    return cut + '…'


def alt_text_x(d, title, vibe, video='tv', limit=ALT_LIMIT, bot_line=False):
    """X video alt text.

    By default this is only the plain screen-reader description. With bot_line=True, append a blank
    line and the full machine-readable data line (' | ' form), keeping the line intact when fitting.
    Returns (text, step)."""
    if not bot_line:
        plain = alt_text(d, title, video)
        if len(plain) <= limit:
            return plain, 'full'
        no_track = alt_text(d, None, video)
        if len(no_track) <= limit:
            return no_track, 'no_track'
        short = _alt_short_warn(d, video)
        if len(short) <= limit:
            return short, 'warn_short'
        return _shorten_words(short, limit), 'plain_cut'
    line = data_line(d, title, vibe)
    sep = '\n\n'
    room = limit - len(line) - len(sep)
    tries = [('full', alt_text(d, title, video)),
             ('no_track', alt_text(d, None, video)),          # the track is also in the data line
             ('warn_short', _alt_short_warn(d, video))]
    for step, plain in tries:
        if len(plain) <= room:
            return plain + sep + line, step
    if room > 20:
        return _shorten_words(tries[-1][1], room) + sep + line, 'plain_cut'
    print(f"WARNING: data line is {len(line)} chars; X alt text is data line only", file=sys.stderr)
    return line, 'line_only'


def _alt_short_warn(d, video):
    dd = dict(d)
    dd['warnings'] = [dict(w, title=short_warning(warning_name(w) or '')) | {'key': None, 'code': None}
                      for w in d.get('warnings') or []]
    return alt_text(dd, None, video)


def _prose_parts(d, title):
    cur, today = d.get('current') or {}, d.get('today') or {}
    temp, cond, when = deg(cur.get('temp')), cur.get('condition'), clock(cur.get('updated'))
    now = now_short = None
    if temp or cond:
        bits = ' and '.join(x for x in (temp, cond.lower() if cond else None) if x)
        now_short = bits[0].upper() + bits[1:] + '.'
        now = bits[0].upper() + bits[1:] + (f" at {when}" if when else '') + '.'
    hi, lo = deg(today.get('high')), deg(today.get('low'))
    hilo = ' · '.join(x for x in (f"High {hi}" if hi else None, f"Low {lo}" if lo else None) if x) or None
    names = [n for n in (warning_name(w) for w in d.get('warnings') or []) if n]
    return dict(now=now, now_short=now_short, hilo=hilo, rain=today.get('chance_of_rain'), names=names)


def build(d, title, tags=True, note=None, line=None, limit=LIMIT):
    """Legacy prose caption (+ optional bot note and data line). limit=None -> never trimmed (long variant)."""
    P = _prose_parts(d, title)
    now, hilo, rain, names = P['now'], P['hilo'], P['rain'], P['names']

    def compose(level):
        L = [opener(d) + (' ' + now if now else '')]
        h = hilo
        if h and rain and level < 1:
            h += f" · {rain} chance of rain"
        if h:
            L.append(h)
        if names:
            ns = names if level < 2 else [short_warning(n) for n in names]
            if level >= 4:
                ns = ns[:2] + ([f"+{len(ns) - 2} more"] if len(ns) > 2 else [])
            L.append('⚠️ ' + ' · '.join(ns))
        if note:
            L.append(note)
        if title:
            L.append(f"🎵 Temple Street – {title}")
        L.append('Data: HK Observatory')
        if tags and level < 3:
            L.append('#HongKong #HKweather #lofi')
        elif tags and level < 5:
            L.append('#HongKong #HKweather')
        if line:
            L.append(line)
        return '\n'.join(L)

    if limit is None:
        return compose(0)
    for level in range(6):
        s = compose(level)
        if x_len(s) <= limit:
            return s
    return s[:limit // 2]          # unreachable in practice; still under the limit


def build_x(d, title, vibe=None, tags=True, note=None):
    """X caption: friendly, human prose (no data line, no bot note), <= 280 X-weighted.
    Based on the friendly part of caption-long; trimmed in X_STEPS order. `vibe`/`note` are accepted for
    backward compatibility and not used (the data line lives in alt-x, the bot note in caption-long).
    Returns (caption, step used)."""
    P = _prose_parts(d, title)
    names = P['names']
    drop = set()
    s = None
    for step in X_STEPS:
        drop.add(step)
        now = P['now_short'] if 'no_time' in drop else P['now']
        L = [opener(d) + (' ' + now if now else '')]
        if 'no_hilo' not in drop:
            h = P['hilo']
            if P['rain'] and 'no_rain' not in drop:
                h = (h + ' · ' if h else '') + f"{P['rain']} chance of rain"
            if h:
                L.append(h)
        if names:
            ns = names if 'warn_short' not in drop else [short_warning(n) for n in names]
            if 'warn_trim' in drop and len(ns) > 2:
                ns = ns[:2] + [f"+{len(ns) - 2} more"]
            L.append('⚠️ ' + ' · '.join(ns))
        if title and 'no_music' not in drop:
            L.append(f"🎵 Temple Street – {title}")
        if 'no_source' not in drop:
            L.append('Data: HK Observatory')
        if tags and 'no_tags' not in drop:
            L.append('#HongKong #HKweather' if 'tags_short' in drop else '#HongKong #HKweather #lofi')
        s = '\n'.join(L)
        if x_len(s) <= LIMIT:
            return s, step
    while x_len(s) > LIMIT:                       # practically unreachable: cut at a word boundary
        s = s.rsplit(' ', 1)[0].rstrip(' ,·') if ' ' in s else s[:-1]
    print("WARNING: X caption had to be cut mid-text", file=sys.stderr)
    return s + '…' if x_len(s + '…') <= LIMIT else s, 'hard_cut'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('data')
    ap.add_argument('-o', '--out', help="X caption path (default caption-$D.txt next to the data; '-' = stdout only)")
    ap.add_argument('--log', default=LOG)
    ap.add_argument('--title', help='catalogue title to use instead of the logged pick')
    ap.add_argument('--no-tags', action='store_true')
    ap.add_argument('--print', dest='show', choices=['x', 'long', 'alt', 'alt-x', 'all'], default='x',
                    help='what to print on stdout (default x = the X caption, as before)')
    ap.add_argument('--bot-line', action='store_true', default=BOT_FRIENDLY,
                    help='opt in to bot-friendly output: the data line and occasional bot note')
    ap.add_argument('--bot-note', choices=['auto', 'on', 'off'], default='auto',
                    help='with --bot-line: auto = about 1 day in 4, deterministic by date')
    ap.add_argument('--video', choices=['tv', 'card'], default='tv', help='which video the alt texts (alt + alt-x) describe')
    a = ap.parse_args()
    d = json.load(open(a.data))
    title, src, vibe = music_pick(d, a.data, a.log, a.title)
    # Public output is human-friendly by default. Keep the old machine-readable/bot additions
    # available behind an explicit switch for later reuse and for compatibility tests.
    note = bot_note(d, vibe, a.bot_note) if a.bot_line else None
    line = data_line(d, title, vibe) if a.bot_line else None
    cap_x, step = build_x(d, title, vibe, not a.no_tags, note)
    cap_long = build(d, title, not a.no_tags, note, line, limit=None)
    alt = alt_text(d, title, a.video)
    alt_x, alt_step = alt_text_x(d, title, vibe, a.video, bot_line=a.bot_line)
    date = d['date']
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.data)), f"caption-{date}.txt")
    written = []
    if out != '-':
        folder = os.path.dirname(os.path.abspath(out))
        files = [(out, cap_x), (os.path.join(folder, f"caption-x-{date}.txt"), cap_x),
                 (os.path.join(folder, f"caption-long-{date}.txt"), cap_long),
                 (os.path.join(folder, f"alt-{date}.txt"), alt),
                 (os.path.join(folder, f"alt-x-{date}.txt"), alt_x)]
        for path, text in files:
            if path in written:
                continue
            with open(path, 'w') as f:
                f.write(text + '\n')
            written.append(path)
    blocks = {'x': cap_x, 'long': cap_long, 'alt': alt, 'alt-x': alt_x}
    if a.show == 'all':
        print('\n\n'.join(f"=== {k} ===\n{v}" for k, v in blocks.items()))
    else:
        print(blocks[a.show])
    print(f"--- x: {x_len(cap_x)}/{LIMIT} (X-weighted, conservative; fit step: {step}) · long: {x_len(cap_long)} "
          f"({len(cap_long)} chars) · alt: {len(alt)} chars · alt-x: {len(alt_x)}/{ALT_LIMIT} chars ({alt_step}) · data line: {len(line) if line else 0} chars · mood: {MOOD.get(vibe)} ({vibe})"
          f" · bot note: {'yes' if note else 'no'} · music: {src}"
          + ('' if not written else ' · ' + ', '.join(os.path.basename(p) for p in written)), file=sys.stderr)


if __name__ == '__main__':
    main()
