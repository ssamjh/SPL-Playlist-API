# StationPlaylist M3U JSON API

A lightweight Flask API that parses StationPlaylist extended M3U files and exposes them as JSON. Designed to run in Docker with a read-only mount of playlist files.

## Quickstart

```bash
docker compose up -d
```

Place your M3U files in `./playlists/` (or adjust the volume path in `compose.yaml`).

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
  "file_path": "X:\\Spots\\5222.mp3"
}
```

## Query parameters

All filter and sort parameters work on both `/playlist/<date>` and `/playlist/<date>/<hour>`.

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

Override in `compose.yaml` if needed:

```yaml
environment:
  - PLAYLIST_DIR=/custom/path
```

## Notes

- Files are read on every request — no caching or database
- `file_path` values are Windows paths as written in the M3U files (e.g. `X:\Spots\file.mp3`). These are returned as-is and are informational only; the server does not attempt to access them
- Break notes (`type=3`) are included in all responses
