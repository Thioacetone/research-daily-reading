"""Unpack data-only bundles uploaded through the GitHub web interface."""
import json
import re
from pathlib import Path, PurePosixPath
import threading
from zipfile import ZipFile

_lock=threading.Lock()


def ensure_bundled_files(root):
    root=Path(root).resolve()
    # Executable source is installed only by the workflow's explicit step.
    # The web reader must unpack exclusively the named data/image archives.
    archives=sorted(p for p in root.glob('reading-*.zip')
                    if p.name in ('reading-content.zip','reading-ui.zip') or re.fullmatch(r'reading-graphics-\d+\.zip',p.name))
    if not archives:
        return
    state_path=root/'.streamlit-cache'/'bundles.json'
    with _lock:
        try:
            state=json.loads(state_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            state={}
        for archive in archives:
            stamp=[archive.stat().st_mtime_ns,archive.stat().st_size]
            if state.get(archive.name)==stamp and (root/'data/paper-recommendation').is_dir() and (root/'graphics').is_dir():
                continue
            with ZipFile(archive) as bundle:
                entries=bundle.infolist()
                if len(entries)>1000 or sum(e.file_size for e in entries)>120_000_000:
                    raise ValueError('Reading bundle is too large')
                for entry in entries:
                    path=PurePosixPath(entry.filename)
                    if archive.name=='reading-ui.zip' and entry.filename not in (
                            'assets/streamlit-reader.css','assets/reading-navigation.js',
                            'assets/reading-clock.js','assets/streamlit-chrome.css'):
                        raise ValueError('Unexpected file in reading UI bundle')
                    if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                            or not path.parts or path.parts[0] not in ('assets','graphics','data')
                            or path.suffix.lower() not in ('.json','.html','.jpg','.jpeg','.png','.webp','.gif','.bmp','.css','.js')):
                        raise ValueError('Unexpected file in reading bundle')
                    target=root.joinpath(*path.parts).resolve()
                    target.relative_to(root)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(bundle.read(entry))
            state[archive.name]=stamp
        state_path.parent.mkdir(parents=True,exist_ok=True)
        state_path.write_text(json.dumps(state),encoding='utf-8')
