import base64
import csv
import glob
import io
import os
import re
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
from flask import Flask, jsonify, abort, request

app = Flask(__name__)

PLAYLIST_DIR = os.environ.get("PLAYLIST_DIR", "/playlists")
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/media")


def resolve_path(windows_path):
    """Translate a Windows absolute path (e.g. G:\\Spots\\1.mp3) to a container path under MEDIA_ROOT."""
    if not windows_path:
        return None
    # Strip drive letter and leading backslash (e.g. "G:\")
    path = re.sub(r'^[A-Za-z]:\\', '', windows_path)
    # Replace backslashes with forward slashes
    path = path.replace('\\', '/')
    return os.path.join(MEDIA_ROOT, path)

TYPE_LABELS = {
    0: "song",
    1: "spot",
    2: "jingle",
    3: "break_note",
    4: "live_dj",
    5: "stream",
    7: "voice_intro",
    8: "voice_outro",
    9: "voice_track",
    10: "commercial_intro",
    11: "commercial",
}


def parse_filename(filename):
    """Parse 'Feb05-08.M3U' → ('Feb05', '08')"""
    base = os.path.splitext(os.path.basename(filename))[0]
    match = re.match(r'^([A-Za-z]+\d+)-(\d+)$', base)
    if match:
        return match.group(1), match.group(2)
    return None, None


def get_playlists():
    pattern = os.path.join(PLAYLIST_DIR, "*.M3U")
    files = sorted(glob.glob(pattern))
    result = []
    for f in files:
        date, hour = parse_filename(f)
        if date and hour:
            result.append({
                "filename": os.path.basename(f),
                "date": date,
                "hour": hour,
                "url": f"/playlist/{date}/{hour}",
                "entry_count": count_entries(f),
            })
    return result


def count_entries(filepath):
    count = 0
    try:
        with open(filepath, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#EXTINF:"):
                    count += 1
    except OSError:
        pass
    return count


def parse_playlist(filepath):
    entries = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return entries

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r\n")
        if line.startswith("#EXTINF:"):
            # Parse duration and info string
            rest = line[len("#EXTINF:"):]
            comma_idx = rest.find(",")
            if comma_idx == -1:
                i += 1
                continue
            duration_str = rest[:comma_idx]
            info = rest[comma_idx + 1:]

            try:
                duration = float(duration_str)
            except ValueError:
                duration = 0.0

            # Find next non-comment line as file_path
            file_path = ""
            j = i + 1
            while j < len(lines):
                next_line = lines[j].rstrip("\r\n")
                if not next_line.startswith("#"):
                    file_path = next_line
                    i = j  # advance outer loop past the file_path line
                    break
                j += 1

            entry = {"duration": duration, "file_path": file_path, "file_exists": os.path.exists(resolve_path(file_path))}

            # Parse pipe-delimited fields
            if info.startswith("|"):
                parts = info.split("|")
                # parts[0] is empty, parts[1] = field[0], parts[2] = field[1], etc.

                def get(idx):
                    real = idx + 1
                    return parts[real] if real < len(parts) else ""

                entry["artist"] = get(0)
                entry["title"] = get(1)
                entry["category"] = get(2)

                # timed_event_type (field[3])
                try:
                    entry["timed_event_type"] = int(get(3))
                except (ValueError, IndexError):
                    entry["timed_event_type"] = 0

                # timed_event_minute (field[4])
                try:
                    entry["timed_event_minute"] = int(get(4))
                except (ValueError, IndexError):
                    entry["timed_event_minute"] = 0

                # timed_event_second (field[5])
                try:
                    entry["timed_event_second"] = int(get(5))
                except (ValueError, IndexError):
                    entry["timed_event_second"] = 0

                # type (field[6])
                try:
                    entry["type"] = int(get(6))
                except (ValueError, IndexError):
                    entry["type"] = 0

                entry["type_label"] = TYPE_LABELS.get(entry["type"], "unknown")

                # intro (field[7])
                try:
                    entry["intro"] = int(get(7))
                except (ValueError, IndexError):
                    entry["intro"] = -1

                # cue_segue_mode (field[9]): 0 = Studio calculates cue/segue, 1 = use stored %q/%Q values
                try:
                    entry["cue_segue_mode"] = int(get(9))
                except (ValueError, IndexError):
                    entry["cue_segue_mode"] = 0

                # cue_time (field[10])
                try:
                    entry["cue_time"] = int(get(10))
                except (ValueError, IndexError):
                    entry["cue_time"] = 0

                # cue_overlap (field[11])
                try:
                    entry["cue_overlap"] = int(get(11))
                except (ValueError, IndexError):
                    entry["cue_overlap"] = 0

                # segue (field[12])
                try:
                    entry["segue"] = int(get(12))
                except (ValueError, IndexError):
                    entry["segue"] = 0

                entry["other"] = get(13)

                # outro (field[14])
                try:
                    entry["outro"] = int(get(14))
                except (ValueError, IndexError):
                    entry["outro"] = -1

                entry["color"] = get(15)
                entry["client"] = get(16)

                # fade_speed (field[17]): lower = faster natural fade
                try:
                    entry["fade_speed"] = int(get(17))
                except (ValueError, IndexError):
                    entry["fade_speed"] = 0

            if entry.get("type") == 3:
                for key in ("file_path", "file_exists", "duration", "intro", "cue_time", "cue_overlap", "segue", "outro"):
                    entry.pop(key, None)

            entries.append(entry)

        i += 1

    return entries


LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}


TEXT_FIELDS = ("artist", "title", "category")


def filter_entries(entries):
    """Apply ?type=, ?q=, and ?exact= filters from query params."""
    # --- type filter ---
    raw_type = request.args.get("type")
    if raw_type is not None:
        if raw_type.lstrip("-").isdigit():
            type_int = int(raw_type)
        else:
            type_int = LABEL_TO_TYPE.get(raw_type.lower())
            if type_int is None:
                abort(400, description=f"Unknown type label '{raw_type}'. Valid labels: {', '.join(LABEL_TO_TYPE)}")
        entries = [e for e in entries if e.get("type") == type_int]

    exact = request.args.get("exact", "1").lower() not in ("0", "false", "no")

    # --- per-field filters (?artist=, ?title=, ?category=) ---
    for field in TEXT_FIELDS:
        value = request.args.get(field)
        if value is not None:
            if exact:
                entries = [e for e in entries if e.get(field, "").lower() == value.lower()]
            else:
                v_lower = value.lower()
                entries = [e for e in entries if v_lower in e.get(field, "").lower()]

    # --- cross-field search (?q=) ---
    q = request.args.get("q")
    if q is not None:
        if exact:
            entries = [
                e for e in entries
                if any(e.get(f, "").lower() == q.lower() for f in TEXT_FIELDS)
            ]
        else:
            q_lower = q.lower()
            entries = [
                e for e in entries
                if any(q_lower in e.get(f, "").lower() for f in TEXT_FIELDS)
            ]

    # --- file_exists filter ---
    file_exists_param = request.args.get("file_exists")
    if file_exists_param is not None:
        want = file_exists_param.lower() not in ("0", "false", "no")
        entries = [e for e in entries if e.get("file_exists") == want]

    # --- sorting ---
    sort_key = request.args.get("sort")
    if sort_key is not None:
        reverse = request.args.get("order", "asc").lower() == "desc"
        try:
            entries = sorted(entries, key=lambda e: (e.get(sort_key) is None, e.get(sort_key, "")), reverse=reverse)
        except TypeError:
            # mixed types (e.g. None alongside ints) — stringify fallback
            entries = sorted(entries, key=lambda e: str(e.get(sort_key, "")), reverse=reverse)

    return entries


def find_playlist_file(date, hour):
    """Find the M3U file matching the given date and hour (e.g. 'Feb05', '8' or '08')."""
    hour_padded = hour.zfill(2)
    pattern = os.path.join(PLAYLIST_DIR, f"{date}-{hour_padded}.M3U")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    # Also try unpadded hour
    hour_unpadded = hour.lstrip("0") or "0"
    pattern2 = os.path.join(PLAYLIST_DIR, f"{date}-{hour_unpadded}.M3U")
    matches2 = glob.glob(pattern2)
    return matches2[0] if matches2 else None


@app.route("/")
def index():
    return jsonify(get_playlists())


@app.route("/playlist/<date>")
def playlist_day(date):
    pattern = os.path.join(PLAYLIST_DIR, f"{date}-*.M3U")
    files = sorted(glob.glob(pattern))
    if not files:
        abort(404)
    all_entries = []
    for f in files:
        _, hour = parse_filename(f)
        for entry in parse_playlist(f):
            entry["hour"] = hour
            all_entries.append(entry)
    all_entries = filter_entries(all_entries)
    return jsonify({
        "date": date,
        "entry_count": len(all_entries),
        "entries": all_entries,
    })


@app.route("/playlist/<date>/<hour>")
def playlist(date, hour):
    filepath = find_playlist_file(date, hour)
    if not filepath:
        abort(404)
    entries = parse_playlist(filepath)
    d, h = parse_filename(filepath)
    entries = filter_entries(entries)
    return jsonify({
        "filename": os.path.basename(filepath),
        "date": d,
        "hour": h,
        "entry_count": len(entries),
        "entries": entries,
    })


def load_studio_configs():
    """Discover studios from STUDIO_<NAME>_ENDPOINT environment variables."""
    studios = {}
    for key, value in os.environ.items():
        if key.startswith("STUDIO_") and key.endswith("_ENDPOINT"):
            name = key[len("STUDIO_"):-len("_ENDPOINT")].lower()
            studios[name] = value
    return studios


STUDIO_CONFIGS = load_studio_configs()


def fetch_studio_data(endpoint_url):
    """Fetch raw CSV text from the studio SPL endpoint, handling Basic Auth in the URL."""
    parsed = urlparse(endpoint_url)
    username = parsed.username
    password = parsed.password

    # Rebuild URL without embedded credentials
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"

    query = parsed.query or ""
    if "TrackInfo=all" not in query:
        query = (query + "&TrackInfo=all") if query else "TrackInfo=all"

    clean_url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, query, parsed.fragment))

    req = Request(clean_url)
    if username is not None:
        credentials = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        req.add_header("Authorization", f"Basic {credentials}")

    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_studio_data(text):
    """Parse SPL CSV output into a list of track dicts."""
    entries = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < 10:
            continue
        try:
            index = int(row[0])
            track_type = int(row[1])
        except ValueError:
            continue

        artist = row[2]
        title = row[3]
        album = row[4]
        duration_ms = int(row[5]) if row[5].lstrip("-").isdigit() else 0
        intro_ms = int(row[6]) if row[6].lstrip("-").isdigit() else -1
        outro_ms = int(row[7]) if row[7].lstrip("-").isdigit() else -1
        category = row[8]
        filename = row[9]

        entry = {
            "index": index,
            "type": track_type,
            "type_label": TYPE_LABELS.get(track_type, "unknown"),
        }

        if artist:
            entry["artist"] = artist
        if title:
            entry["title"] = title
        if album:
            entry["album"] = album

        entry["duration"] = duration_ms / 1000.0

        if intro_ms != -1:
            entry["intro"] = intro_ms
        if outro_ms != -1:
            entry["outro"] = outro_ms

        if category:
            entry["category"] = category

        if filename:
            entry["filename"] = filename
            entry["file_exists"] = os.path.exists(resolve_path(filename))

        # Strip playback fields from break notes and hour markers
        if track_type == 3:
            for key in ("duration", "intro", "outro", "filename", "file_exists"):
                entry.pop(key, None)
        elif track_type == 4:
            entry.pop("duration", None)

        entries.append(entry)

    return entries


def parse_hour_from_marker(title):
    """Extract hour (int) from an Hour Marker title like '1200 (12pm 23/02/2026)'."""
    m = re.match(r'^(\d{2})\d{2}', title.strip())
    return int(m.group(1)) if m else None


def assign_hours(entries):
    """Tag each entry with the hour it falls under, based on Hour Marker entries."""
    current_hour = None
    for entry in entries:
        if entry.get("category") == "Hour Marker":
            current_hour = parse_hour_from_marker(entry.get("title", ""))
        entry["hour"] = current_hour
    return entries


@app.route("/studio/<studio_name>")
def studio(studio_name):
    config = STUDIO_CONFIGS.get(studio_name.lower())
    if config is None:
        abort(404, description=f"Studio '{studio_name}' not configured.")

    try:
        text = fetch_studio_data(config)
    except Exception as e:
        abort(502, description=f"Failed to fetch studio data: {e}")

    entries = parse_studio_data(text)
    entries = assign_hours(entries)

    hour_param = request.args.get("hour")
    if hour_param is not None:
        try:
            hour_int = int(hour_param)
        except ValueError:
            abort(400, description="Invalid hour parameter, expected an integer.")
        entries = [e for e in entries if e.get("hour") == hour_int]

    entries = filter_entries(entries)

    return jsonify({
        "studio": studio_name.lower(),
        "entry_count": len(entries),
        "entries": entries,
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
