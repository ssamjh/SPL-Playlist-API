# StationPlaylist M3U JSON API

A lightweight Flask API that parses StationPlaylist extended M3U files and exposes them as JSON. Designed to run in Docker with a read-only mount of playlist files.

## Quickstart

```bash
docker compose up -d
```

Place your M3U files in `./playlists/` (or adjust the volume path in `docker-compose.yaml`).

## File naming convention

Files must follow the pattern `<Date>-<HH>.M3U`, e.g.:

```
Feb05-08.M3U
Feb05-09.M3U
Feb06-14.M3U
```

All matching files in the mounted directory are picked up automatically.

The date part is read using the [strftime](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes) pattern in `PLAYLIST_DATE_FORMAT` (default `%b%d`), so a backend writing a different format is a config change rather than a code change:

| `PLAYLIST_DATE_FORMAT` | Matches |
|------------------------|---------|
| `%b%d` (default) | `Feb05-08.M3U` |
| `%Y-%m-%d` | `2026-02-05-08.M3U` |
| `%y%m%d` | `260205-08.M3U` |
| `%d%b` | `05Feb-08.M3U` |
| `%m-%d` | `09-01-01.M3U` |

The hour is always the final `-` separated segment, so formats containing `-` work fine.

**URLs and responses always use `MmmDD`** (e.g. `Feb05`) no matter what is on disk — the API translates between the two. URLs in the configured on-disk format are also accepted. Since `MmmDD` carries no year, it resolves against the current year when the on-disk format needs one.

### Worked example: `09-01-01.M3U` (1am, 1 September)

```yaml
environment:
  - PLAYLIST_DATE_FORMAT=%m-%d
```

The hour is the last `-` segment, so `09-01-01` splits into date `09-01` and hour `01`. Note the hour is a separate path segment in the URL — `/playlist/09-01/01`, not `/playlist/09-01-01`.

| URL | |
|-----|---|
| `/playlist/09-01/01` | Single hour |
| `/playlist/09-01/1` | Same file — unpadded hour |
| `/playlist/Sep01/1` | Same file — canonical `MmmDD` |
| `/playlist/09-01` or `/playlist/Sep01` | Whole day |

`GET /` reports it as:

```json
{
  "filename": "09-01-01.M3U",
  "date": "Sep01",
  "hour": "01",
  "url": "/playlist/Sep01/01"
}
```

If your `09-01` is day-month (1 September written `DD-MM`) rather than month-day, use `%d-%m` instead. Both match this particular file, but they diverge on any day past the 12th.


## Endpoints

### `GET /`
Lists all available playlists.

```json
[
  {
    "filename": "Feb05-08.M3U",
    "date": "Feb05",
    "hour": "08",
    "url": "/playlist/Feb05/08",
    "entry_count": 104
  }
]
```

---

### `GET /playlist/<date>`
Returns all entries for an entire day across every hour file.

```
/playlist/Feb05
```

Each entry includes an `"hour"` field indicating which file it came from.

---

### `GET /playlist/<date>/<hour>`
Returns entries for a single hour. Accepts zero-padded or unpadded hour (`08` or `8`).

```
/playlist/Feb05/08
/playlist/Feb05/8
```

**Example entry:**
```json
{
  "duration": 21.912,
  "artist": "Some Artist",
  "title": "Some Title",
  "category": "<Comm Break=00>",
  "type": 11,
  "type_label": "commercial",
  "intro": -1,
  "cue_time": 500,
  "cue_overlap": 2700,
  "segue": 19600,
  "replay_gain": -6.35,
  "file_path": "X:\\Spots\\5222.mp3",
  "file_exists": true
}
```

`replay_gain` is the ReplayGain level in dB written into the audio file by Track Tool's
Gain Scan — the gain Studio applies on playback to even out loudness between tracks. It
appears **only when `?replay_gain=1` is passed**, since reading it opens every entry's
file. See [ReplayGain](#replaygain).

---

### `GET /studio/<studio_name>`
Returns the track list currently loaded in a studio's SPL instance. The data is fetched live from the SPL HTTP endpoint each request.

```
/studio/main
/studio/main?hour=12
```

**Example response:**
```json
{
  "studio": "main",
  "current_index": 5,
  "entry_count": 13,
  "entries": [
    {
      "index": 0,
      "type": 4,
      "type_label": "live_dj",
      "title": "1200 (12pm 01/01/2025)",
      "category": "Hour Marker",
      "filename": "X:\\Playlist\\Playlists\\Jan01-12.m3u",
      "file_exists": false,
      "hour": 12
    },
    {
      "index": 2,
      "type": 11,
      "type_label": "commercial",
      "artist": "Some Advertiser",
      "title": "Some Spot Title",
      "duration": 19.1,
      "category": "<Comm Break=00>",
      "filename": "X:\\Spots\\1234.mp3",
      "file_exists": true,
      "hour": 12
    }
  ]
}
```

**Response fields:**

| Field | Description |
|-------|-------------|
| `studio` | Studio name (lowercased) |
| `current_index` | Index of the currently playing track (`null` if unavailable) |
| `entry_count` | Number of entries returned |

**Entry fields** (keys omitted when empty or not applicable):

| Field | Description |
|-------|-------------|
| `index` | Position in the loaded playlist |
| `type` | Track type integer |
| `type_label` | Human-readable type (see type reference above) |
| `artist` | Artist name |
| `title` | Track title |
| `album` | Album name |
| `duration` | Duration in seconds (omitted for `break_note` and `live_dj`) |
| `intro` | Intro time in ms (omitted if `-1`) |
| `outro` | Outro time in ms (omitted if `-1`) |
| `replay_gain` | ReplayGain level in dB — only when `?replay_gain=1` is passed, and omitted if the file has no ReplayGain tag |
| `category` | SPL category string |
| `filename` | Windows file path as reported by SPL |
| `file_exists` | Whether the file is accessible from within the container (omitted for `break_note`) |
| `hour` | Hour block the entry falls under, parsed from Hour Marker entries (`null` if before the first marker) |

**`?hour=` parameter:**

Filter results to a single hour block. The hour is an integer matching the first two digits of the Hour Marker time (e.g. `12` for a marker titled `1200 (12pm ...)`).

```
/studio/main?hour=12
/studio/main?hour=8
```

All standard filter, search, and sort parameters also apply — see [Query parameters](#query-parameters) below.

---

## ReplayGain

`replay_gain` is the ReplayGain track gain in dB (e.g. `-10.01`, `1.36`) that Track Tool's
*Gain Scan* wrote into the audio file, and that Studio applies on playback to normalise
loudness. It is available on `/playlist/<date>`, `/playlist/<date>/<hour>` and
`/studio/<studio_name>`.

### `?replay_gain=1` (opt-in — required)

Reading the gain means opening every entry's audio file, so it is **off by default** and
must be requested explicitly. Without the parameter the key is never present.

```
/playlist/Feb05/08?replay_gain=1
/studio/main?replay_gain=1
/playlist/Feb05?replay_gain=1&type=song&sort=replay_gain
```

| Param | Default | Description |
|-------|---------|-------------|
| `?replay_gain=` | `0` | `1`/`true` = read and include `replay_gain`, `0` = omit it |

Values are cached per `(path, mtime)`, so the cost lands on the first request for a given
file and later requests are cheap. Gain is read **before** filtering and sorting so
`?sort=replay_gain` works — which also means combining it with `?type=` still reads every
entry's file, not just the matching ones.

The value is **not** in the M3U or in the SPL database — it is read from the audio file
itself, so the drive holding the file must be mounted (see
[Media roots](#media-roots)) for the field to appear. Details:

- Track Tool stores it in an **APEv2 tag** at the end of the file, for `.wav` as well as
  `.mp3`. Studio also writes its own binary items into that same tag, which makes strict
  APEv2 libraries reject the whole tag — so the reader locates just the
  `REPLAYGAIN_TRACK_GAIN` item rather than parsing every item
- An `ID3v1` tag appended after the APEv2 footer is handled
- The key is **omitted** when the file has no ReplayGain tag (i.e. it was never gain
  scanned) or cannot be read. It is never reported as `0`, since 0 dB is a valid gain

You can use this to find tracks that were missed by a gain scan:

```
/playlist/Feb05?replay_gain=1&type=song&sort=replay_gain
```

---

## Query parameters

All filter and sort parameters work on `/playlist/<date>`, `/playlist/<date>/<hour>`, and `/studio/<studio_name>`.

### Filtering by type

| Param | Description |
|-------|-------------|
| `?type=<value>` | Filter by type integer or label string |

```
?type=11
?type=commercial
```

**Type reference:**

| Value | Label |
|-------|-------|
| 0 | song |
| 1 | spot |
| 2 | jingle |
| 3 | break_note |
| 4 | live_dj |
| 5 | stream |
| 7 | voice_intro |
| 8 | voice_outro |
| 9 | voice_track |
| 10 | commercial_intro |
| 11 | commercial |

---

### Filtering by text fields

Filter on `artist`, `title`, or `category` individually. By default matching is **exact** (case-insensitive). Add `?exact=0` for substring search.

```
?artist=John Farnham
?category=80s-Power
?title=Far Away&exact=0
```

Use `?q=` to search across all three text fields at once:

```
?q=Power&exact=0
```

| Param | Default | Description |
|-------|---------|-------------|
| `?artist=` | — | Match artist field |
| `?title=` | — | Match title field |
| `?category=` | — | Match category field |
| `?q=` | — | Match any of artist, title, category |
| `?exact=` | `1` | `1` = exact match, `0` = substring |

---

### Sorting

```
?sort=artist
?sort=duration&order=desc
?sort=type&order=asc
```

| Param | Default | Description |
|-------|---------|-------------|
| `?sort=` | — | Any entry key to sort by |
| `?order=` | `asc` | `asc` or `desc` |

---

### Filtering by file existence

```
?file_exists=true
?file_exists=false
```

| Param | Description |
|-------|-------------|
| `?file_exists=` | `true`/`1` = only entries whose file exists on disk, `false`/`0` = only missing files |

Entries with a missing value for the sort key are placed last.

---

### Combining parameters

All parameters can be combined freely:

```
/playlist/Feb05?type=song&category=80s-Power&sort=duration&order=desc
/playlist/Feb05/08?type=commercial&artist=Some Artist&exact=0
```

---

## Log endpoints

SPL Studio writes a `SLog-YYMMDD.csv` file per day containing every track, spot, jingle, break note, and system event. Use the `?type=` filter to narrow results (e.g. songs only, commercials only).

---

### `GET /logs/<studio_name>`
Lists all available SLog files for the studio.

```
/logs/main
```

```json
{
  "studio": "main",
  "entry_count": 2,
  "files": [
    { "date": "260322", "filename": "SLog-260322.csv" },
    { "date": "260323", "filename": "SLog-260323.csv" }
  ]
}
```

---

### `GET /logs/<studio_name>/<date>`
Returns entries from the SLog for the given date.

```
/logs/main/260323
/logs/main/2026-03-23
```

**Accepted date formats:**

| Format | Example |
|--------|---------|
| `YYMMDD` | `260323` |
| `YYYY-MM-DD` | `2026-03-23` |

**Example response:**
```json
{
  "studio": "main",
  "date": "260323",
  "entry_count": 312,
  "entries": [
    {
      "date": "23/03/2026",
      "time": "00:00:40",
      "studio": "Studio 1",
      "type": 8,
      "type_label": "event",
      "message": "------------- Hour Marker -------------",
      "detail": "0000 (12am 23/03/2026)"
    },
    {
      "date": "23/03/2026",
      "time": "00:00:57",
      "studio": "Studio 1",
      "type": 0,
      "type_label": "general_track",
      "artist": "Some Artist",
      "title": "Some Title",
      "duration": "04:45",
      "category": "Music-80s",
      "file_path": "G:\\Music\\Some Artist - Some Title.wav",
      "album": "Some Album",
      "year": "1985",
      "label": "Some Label",
      "isrc": "ABCD01234567",
      "scheduled_time": "23/03/2026 00:00"
    }
  ]
}
```

**Entry fields** (keys omitted when empty or not applicable):

| Field | Description |
|-------|-------------|
| `date` | Date the entry was logged (`DD/MM/YYYY`) |
| `time` | Time the entry was logged (`HH:MM:SS`) |
| `studio` | Studio name as configured in SPL |
| `type` | Log entry type integer (see type reference below) |
| `type_label` | Human-readable type label |
| `artist` | Artist name (track entries only) |
| `title` | Track title |
| `duration` | Duration string (`MM:SS`) |
| `category` | SPL category |
| `file_path` | Windows file path as logged by SPL |
| `album` | Album name |
| `year` | Release year |
| `composer` | Composer |
| `label` | Record label |
| `isrc` | ISRC code or cart/spot number |
| `scheduled_time` | Time the track was scheduled (`DD/MM/YYYY HH:MM`) |
| `message` | Event description (type 8 entries only) |
| `detail` | Additional event detail (type 8 entries only, omitted if absent) |

**SLog type reference:**

| Value | Label | Description |
|-------|-------|-------------|
| 0 | `general_track` | Songs and general audio tracks |
| 1 | `general_spot` | Jingles, sweepers, and general spots |
| 2 | `voice_track` | Voice tracks, voice intros and outros |
| 3 | `break_note` | Non-audio break notes and executables |
| 4 | `cart` | Carts |
| 5 | `commercial` | Commercials |
| 6 | `system` | Studio monitor, TCP connections, serial port |
| 7 | `skipped` | Tracks skipped at the end of an hour |
| 8 | `event` | Misc events (playlist loaded, hour markers, etc.) |
| 9 | `error_warning` | Important warnings and errors |

**Query parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `?type=` | — | Filter by type integer or label |
| `?artist=` | — | Match artist field |
| `?title=` | — | Match title field |
| `?q=` | — | Match either artist or title |
| `?exact=` | `1` | `1` = exact (case-insensitive), `0` = substring |

```
/logs/main/260323?type=general_track
/logs/main/260323?type=5
/logs/main/260323?artist=Fleetwood Mac
/logs/main/260323?q=fleetwood&exact=0
```

---

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `PLAYLIST_DIR` | `/playlists` | Path to the directory containing M3U files |
| `PLAYLIST_DATE_FORMAT` | `%b%d` | strftime pattern for the date part of M3U filenames (see [File naming convention](#file-naming-convention)) |
| `MEDIA_ROOT_<LETTER>` | — | Container path that Windows drive `<LETTER>:` is mounted at |
| `MEDIA_ROOT` | `/media` | Fallback mount for drive letters with no `MEDIA_ROOT_<LETTER>` |
| `STUDIO_<NAME>_ENDPOINT` | — | SPL HTTP endpoint URL for a studio (see below) |
| `STUDIO_<NAME>_LOG_DIR` | — | Log directory for a studio (see below) |

### Studio endpoints

Add one `STUDIO_<NAME>_ENDPOINT` variable per studio. The `<NAME>` portion (uppercased) becomes the studio name used in the URL path. Basic Auth credentials can be embedded directly in the URL.

```yaml
environment:
  - STUDIO_MAIN_ENDPOINT=http://studio:admin@192.168.1.20:8080/
  - STUDIO_BACKUP_ENDPOINT=http://studio:admin@192.168.1.22:8080/
```

This exposes `/studio/main` and `/studio/backup`. If no studio variables are defined the endpoint is simply unavailable — playlist routes are unaffected.

### Studio log directories

Add one `STUDIO_<NAME>_LOG_DIR` variable per studio pointing to the folder where SPL writes its log files. The `<NAME>` becomes the studio name used in the URL path.

```yaml
environment:
  - STUDIO_MAIN_LOG_DIR=/logs/main
  - STUDIO_BACKUP_LOG_DIR=/logs/backup
```

This exposes `/logs/main` and `/logs/backup`. Mount each log folder as a volume:

```yaml
volumes:
  - /path/to/main/logs:/logs/main:ro
  - /path/to/backup/logs:/logs/backup:ro
```

### Media roots

Windows paths in M3U, studio and log data (e.g. `G:\Music\...`, `H:\Archive\...`) are
resolved to container paths in order to serve `file_exists` and `replay_gain`. The **drive
letter** selects the mount, so each drive that appears in your paths needs one
`MEDIA_ROOT_<LETTER>` variable and a matching volume:

```yaml
volumes:
  - /mnt/whiti-g:/media-g:ro
  - /mnt/whiti-h:/media-h:ro
environment:
  - MEDIA_ROOT_G=/media-g
  - MEDIA_ROOT_H=/media-h
```

With the above, `G:\Music\song.wav` resolves to `/media-g/Music/song.wav` and
`H:\Archive\clip.wav` to `/media-h/Archive/clip.wav`. The letter is matched
case-insensitively.

Any drive letter without its own variable falls back to `MEDIA_ROOT`. If you only have one
media drive, `MEDIA_ROOT` alone is still enough — the per-drive variables are optional.

A drive that is referenced but not mounted is not an error: those entries simply report
`file_exists: false` and carry no `replay_gain`.

## Notes

- Files are read on every request — no caching or database
- `file_path` values are Windows paths as written in the M3U or log files. These are returned as-is
- `file_exists` is `true` if the file at `file_path` is accessible from within the container. The Windows drive letter selects its mount and the remaining path is resolved under it (e.g. `G:\Music\song.wav` → `/media-g/Music/song.wav`) — see [Media roots](#media-roots)
- `replay_gain` is only present when `?replay_gain=1` is passed — see [ReplayGain](#replaygain)
- `break_note` entries (type 3) omit `file_path`, `file_exists`, `duration`, `intro`, `cue_time`, `cue_overlap`, `segue`, and `replay_gain` as these fields are not applicable
- In studio responses, `break_note` entries (type 3) omit `duration`, `intro`, `outro`, `filename`, and `file_exists`; `live_dj` entries (type 4) omit `duration`
- Studio data is fetched live on every request — SPL must be reachable from the container at request time
- Log files are expected to be in UTF-8 encoding as written by SPL Studio
