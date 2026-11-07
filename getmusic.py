#!/usr/bin/env python3
"""Offline Music downloader for a-Shell on iPhone (no Mac needed).

  python3 ~/Documents/offline-music/getmusic.py "<YouTube Music link, or a song to search>"

Downloads the song / album / playlist and packs it into one file in
Files -> On My iPhone -> a-Shell -> Music Inbox, which the Music app's Import button reads.
Songs you've downloaded before are skipped (add --again to fetch them anyway), but a
playlist's full song order is always included, so re-sharing a playlist keeps it up to date.
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import zipfile

import yt_dlp

DOCS = os.environ.get("OM_HOME") or os.path.expanduser("~/Documents")
INBOX = os.path.join(DOCS, "Music Inbox")
DATA = os.path.join(DOCS, "offline-music")
ARCHIVE = os.path.join(DATA, "downloaded.txt")


def is_playlist_url(q):
    if "/browse/" in q or "/playlist" in q:
        return True
    return "list=" in q and "watch?" not in q


def read_playlist(url):
    """Title, id and song order of a playlist/album, without downloading (needs no JS)."""
    opts = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True,
            "skip_download": True, "ignoreerrors": True}
    for _ in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # network blips: try once more
            print("Couldn't read the playlist yet (%s), retrying…" % e)
            continue
        ids = [e["id"] for e in (info or {}).get("entries") or [] if e and e.get("id")]
        if ids:
            return {"id": info.get("id"), "title": info.get("title"), "ids": ids}
    return None


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", s or "").strip()
    return re.sub(r"\s+", " ", s)[:80] or "Music"


def main(argv):
    again = "--again" in argv
    args = [a for a in argv if a != "--again"]
    if not args or not args[0].strip():
        print(__doc__)
        return 1
    q = " ".join(args).strip()
    if q.endswith(" --again"):   # the Shortcut passes everything as one piece of text
        again, q = True, q[:-len(" --again")].strip()
    is_url = re.match(r"^https?://", q) is not None
    target = q if is_url else \
        "https://music.youtube.com/search?q=" + urllib.parse.quote(q) + "#songs"

    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    work = os.path.join(DATA, "work-%d" % time.time())
    os.makedirs(work)
    log = os.path.join(work, "tracks.jsonl")

    pl = None
    if is_url and is_playlist_url(q):
        print("Reading the playlist…")
        pl = read_playlist(q)
        if pl:
            print("“%s”: %d songs" % (pl["title"], len(pl["ids"])))

    cmd = [
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "--write-thumbnail",
        "-P", work,
        "-o", "%(id)s.%(ext)s",
        "-o", "thumbnail:%(id)s.%(ext)s",
        "--ignore-errors", "--no-overwrites", "--no-mtime",
        "--print-to-file",
        "after_move:%(.{id,title,track,artist,artists,album,duration,filepath,uploader})j", log,
    ]
    if not again:
        cmd += ["--download-archive", ARCHIVE]
    if not is_url:
        cmd += ["--playlist-items", "1"]
    elif "watch?" in q and "v=" in q:
        cmd += ["--no-playlist"]   # a song link with &list=RD... is an endless radio mix
    cmd.append(target)

    try:
        yt_dlp.main(cmd)
    except SystemExit:
        pass   # yt-dlp always exits; errors for single songs were already printed

    tracks = []
    try:
        with open(log) as f:
            lines = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        lines = []
    for info in lines:
        path = info.get("filepath") or ""
        if not os.path.exists(path):
            continue
        vid = info["id"]
        cover = next((vid + e for e in (".jpg", ".webp", ".png")
                      if os.path.exists(os.path.join(work, vid + e))), None)
        artists = info.get("artists") or []
        tracks.append({
            "id": vid,
            "title": info.get("track") or info.get("title") or vid,
            "artist": info.get("artist") or (", ".join(artists) if artists else None)
                      or info.get("uploader") or "Unknown artist",
            "album": info.get("album") or "",
            "duration": info.get("duration") or 0,
            "file": os.path.basename(path),
            "cover": cover,
        })

    playlists = []
    if pl:
        name = re.sub(r"^Album - ", "", pl["title"] or "YouTube playlist")
        playlists.append({"id": "yt-" + (pl["id"] or str(int(time.time()))), "name": name,
                          "tracks": pl["ids"], "updated": int(time.time() * 1000)})

    if not tracks and not playlists:
        shutil.rmtree(work, ignore_errors=True)
        print("\nNothing new to import - already downloaded, or nothing found.")
        print("(Add --again to download songs you've had before.)")
        return 0

    if playlists:
        label = playlists[0]["name"]
    elif len(tracks) == 1:
        label = "%s - %s" % (tracks[0]["artist"], tracks[0]["title"])
    else:
        label = "Download"
    zname = "%s %s.zip" % (safe_name(label), time.strftime("%m-%d %H.%M"))
    manifest = {"format": "offline-music", "version": 1, "created": int(time.time()),
                "source": q, "tracks": tracks, "playlists": playlists}
    zpath = os.path.join(INBOX, zname)
    with zipfile.ZipFile(zpath + ".part", "w", zipfile.ZIP_STORED) as z:
        z.writestr("offline-music.json", json.dumps(manifest, ensure_ascii=False))
        for t in tracks:
            for key in ("file", "cover"):
                if t.get(key):
                    z.write(os.path.join(work, t[key]), t[key])
    os.replace(zpath + ".part", zpath)
    shutil.rmtree(work, ignore_errors=True)

    print("\n✅ %d new song%s%s" % (len(tracks), "" if len(tracks) == 1 else "s",
                                   " · playlist “%s”" % playlists[0]["name"] if playlists else ""))
    print("Saved: Music Inbox/%s" % zname)
    print("Now open Music → Add → Import, and pick that file.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
