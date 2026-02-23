# StationPlaylist M3U JSON API

A lightweight Flask API that parses StationPlaylist extended M3U files and exposes them as JSON. Designed to run in Docker with a read-only mount of playlist files.

## Quickstart

```bash
docker compose up -d
```

Place your M3U files in `./playlists/` (or adjust the volume path in `docker-compose.yaml`).

## File naming convention

Files must follow the pattern `<MonthDay>-<HH>.M3U`, e.g.:

```
Feb05-08.M3U
Feb05-09.M3U
Feb06-14.M3U
```

All matching files in the mounted directory are picked up automatically.


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
  "file_path": "X:\\Spots\\5222.mp3",
  "file_exists": true
}
```

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
  "entry_count": 13,
  "entries": [
    {
      "index": 0,
      "type": 4,
      "type_label": "live_dj",
      "title": "1200 (12pm 01/01/2025)",
      "category": "Hour Marker",
      "filename": "G:\\Playlist\\Playlists\\Jan01-12.m3u",
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
      "filename": "G:\\Spots\\1234.mp3",
      "file_exists": true,
      "hour": 12
    }
  ]
}
```

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

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `PLAYLIST_DIR` | `/playlists` | Path to the directory containing M3U files |
| `MEDIA_ROOT` | `/media` | Container path that the Windows drive root is mounted at |
| `STUDIO_<NAME>_ENDPOINT` | — | SPL HTTP endpoint URL for a studio (see below) |

### Studio endpoints

Add one `STUDIO_<NAME>_ENDPOINT` variable per studio. The `<NAME>` portion (uppercased) becomes the studio name used in the URL path. Basic Auth credentials can be embedded directly in the URL.

```yaml
environment:
  - STUDIO_MAIN_ENDPOINT=http://studio:admin@192.168.1.20:8080/
  - STUDIO_BACKUP_ENDPOINT=http://studio:admin@192.168.1.22:8080/
```

This exposes `/studio/main` and `/studio/backup`. If no studio variables are defined the endpoint is simply unavailable — playlist routes are unaffected.

The `MEDIA_ROOT` variable is used to resolve `file_exists`. Windows paths in M3U files (e.g. `X:\Music\...`) have their drive letter stripped and are looked up under `MEDIA_ROOT`. Mount the root of your media drive to match:

```yaml
volumes:
  - /mnt/your-drive:/media:ro
environment:
  - MEDIA_ROOT=/media
```

## Notes

- Files are read on every request — no caching or database
- `file_path` values are Windows paths as written in the M3U files (e.g. `X:\Spots\file.mp3`). These are returned as-is
- `file_exists` is `true` if the file at `file_path` is accessible from within the container. The Windows drive letter is stripped and the remaining path is resolved under `MEDIA_ROOT` (e.g. `X:\Music\song.wav` → `/media/Music/song.wav`)
- `break_note` entries (type 3) omit `file_path`, `file_exists`, `duration`, `intro`, `cue_time`, `cue_overlap`, and `segue` as these fields are not applicable
- In studio responses, `break_note` entries (type 3) omit `duration`, `intro`, `outro`, `filename`, and `file_exists`; `live_dj` entries (type 4) omit `duration`
- Studio data is fetched live on every request — SPL must be reachable from the container at request time
