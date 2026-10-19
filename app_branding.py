"""Rotate original artwork and derive readable page palettes without altering images."""
import base64
import colorsys
from functools import lru_cache
import html
import json
import mimetypes
import os
from pathlib import Path
import random
import re
import threading
from urllib.parse import quote

ROOT=Path(__file__).resolve().parent
ARTWORK=ROOT/'assets'/'program-art.jpg'
GRAPHICS=ROOT/'graphics'
_IMAGE_TYPES={'.jpg','.jpeg','.png','.webp','.gif','.bmp'}
_lock=threading.Lock()
_deck=[]
_last=''
_signature=()


def _hex(rgb):
    return '#'+''.join(f'{max(0,min(255,round(c))):02x}' for c in rgb)


def _rgb(color):
    return tuple(int(color[i:i+2],16) for i in (1,3,5))


def contrast(left,right):
    def luminance(color):
        parts=[v/255 for v in _rgb(color)]
        parts=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in parts]
        return sum(a*b for a,b in zip(parts,(.2126,.7152,.0722)))
    a,b=sorted((luminance(left),luminance(right)))
    return (b+.05)/(a+.05)


def _tint(rgb,white):
    return _hex(tuple(v*(1-white)+255*white for v in rgb))


def palette_from_rgb(rgb):
    h,_,s=colorsys.rgb_to_hls(*(v/255 for v in rgb))
    s=max(.25,min(.68,s))
    def shade(light,saturation=s):return _hex(tuple(v*255 for v in colorsys.hls_to_rgb(h,light,saturation)))
    accent=shade(.32)
    light=.32
    while contrast(accent,'#ffffff')<4.8 and light>.15:
        light-=.01;accent=shade(light)
    return {'accent':accent,'hero':shade(.17,min(s,.42)),'background':_tint(rgb,.955),
            'panel':_tint(rgb,.985),'tint':_tint(rgb,.89),'border':_tint(rgb,.72),
            'text':shade(.13,.19),'muted':shade(.34,.12),'seed':_hex(rgb)}


@lru_cache(maxsize=256)
def _analyze(path,mtime,size):
    # Sampling is for color analysis only. Original pictures are never saved or changed.
    try:
        from PIL import Image,ImageOps
        with Image.open(path)as source:
            image=ImageOps.exif_transpose(source).convert('RGBA')
            image.thumbnail((96,96))
            bins={}
            pixels=image.get_flattened_data()if hasattr(image,'get_flattened_data')else image.getdata()
            for red,green,blue,alpha in pixels:
                if alpha<128:continue
                h,s,v=colorsys.rgb_to_hsv(red/255,green/255,blue/255)
                if s<.16 or v<.17 or (v>.96 and s<.24):continue
                key=(int(h*24)%24,int(s*3),int(v*3))
                weight=(.35+s)*(.5+v)
                count,rr,gg,bb=bins.get(key,(0,0,0,0))
                bins[key]=(count+weight,rr+red*weight,gg+green*weight,bb+blue*weight)
            if bins:
                count,*total=max(bins.values(),key=lambda entry:entry[0])
                return palette_from_rgb(tuple(v/count for v in total))
    except (ImportError,OSError,ValueError):pass
    return palette_from_rgb((126,145,156))


def artwork_catalog():
    files=[]
    if GRAPHICS.is_dir():
        for path in sorted(GRAPHICS.rglob('*')):
            if path.is_file()and path.suffix.lower()in _IMAGE_TYPES:
                try:path.resolve().relative_to(GRAPHICS.resolve())
                except ValueError:continue
                files.append(path)
    if not files and ARTWORK.is_file():files=[ARTWORK]
    result=[]
    for path in files:
        stat=path.stat()
        result.append({'id':path.relative_to(ROOT).as_posix(),'path':path,
                       'theme':dict(_analyze(str(path),stat.st_mtime_ns,stat.st_size))})
    return result


def choose_artwork():
    global _signature,_deck,_last
    entries=artwork_catalog()
    if not entries:return None
    current=tuple(e['id']for e in entries)
    with _lock:
        if current!=_signature:_signature=current;_deck=[]
        if not _deck:
            _deck=list(current);random.SystemRandom().shuffle(_deck)
            if len(_deck)>1 and _deck[-1]==_last:_deck[0],_deck[-1]=_deck[-1],_deck[0]
        selected=_deck.pop();_last=selected
    return next(e for e in entries if e['id']==selected)


def theme_css(theme):
    variables=';'.join('--reading-'+k+':'+v for k,v in theme.items())
    return ':root{'+variables+'}'+(ROOT/'assets'/'reading-theme.css').read_text(encoding='utf-8')


def _url(path,directory,embed=False):
    if embed:
        mime=mimetypes.guess_type(path.name)[0]or'image/jpeg'
        return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')
    try:return quote(Path(os.path.relpath(path,Path(directory))).as_posix(),safe='/.')
    except ValueError:return path.as_uri()


def layout_preview_hero(document,art):
    """Keep the title and artwork in separate, responsive header columns."""
    def arrange(match):
        copy=re.sub(r'<img\b[^>]*\bid="reading-artwork"[^>]*>', '', match['copy'])
        return (match['open']+'<div class="reading-hero-layout">'
                '<div class="reading-hero-copy">'+copy+'</div>'
                '<figure class="reading-hero-visual">'+art+'</figure></div></td>')
    return re.sub(r'(?P<open><td\b[^>]*\bclass=[\'"]hero-pad[\'"][^>]*>)(?P<copy>.*?)</td>',
                  arrange,document,count=1,flags=re.S|re.I)


def unbrand_preview(document):
    """Replace saved preview branding without nesting headers or stale artwork."""
    document=re.sub(r'<link\b[^>]*\bid="reading-(?:favicon|touch-icon)"[^>]*>', '', document)
    document=re.sub(r'<style id="reading-theme">.*?</style>', '', document, flags=re.S)
    document=re.sub(r'<script id="reading-artwork-catalog"[^>]*>.*?</script>\s*<script>.*?</script>',
                    '',document,flags=re.S)
    document=re.sub(r'<div class="reading-hero-layout"><div class="reading-hero-copy">(.*?)</div>'
                    r'<figure class="reading-hero-visual">.*?</figure></div>',r'\1',document,flags=re.S)
    return re.sub(r'<img\b[^>]*\bid="reading-artwork"[^>]*>', '', document)


def brand_preview(document,directory,artwork=None,embed_image=False):
    entries=artwork_catalog()
    if artwork is not None:
        entries=[e for e in entries if e['id']==artwork['id']]
    if not entries:return document
    document=unbrand_preview(document)
    catalog=[{'id':e['id'],'src':_url(e['path'],directory,embed_image),'theme':e['theme']}for e in entries]
    first=catalog[0];src=html.escape(first['src'],quote=True)
    mime=mimetypes.guess_type(entries[0]['path'].name)[0]or'image/jpeg'
    head=(f'<link id="reading-favicon" rel="icon" type="{mime}" href="{src}">'
          f'<link id="reading-touch-icon" rel="apple-touch-icon" href="{src}">'
          '<style id="reading-theme">'+theme_css(first['theme'])+'</style>')
    document=document.replace('</head>',head+'</head>',1)
    art=f'<img id="reading-artwork" src="{src}" alt="本次阅读配图" width="280" height="280">'
    document=layout_preview_hero(document,art)
    payload=json.dumps({'randomize':artwork is None,'images':catalog},ensure_ascii=False).replace('<','\u003c')
    script=(ROOT/'assets'/'reading-theme.js').read_text(encoding='utf-8')
    return document.replace('</body>','<script id="reading-artwork-catalog" type="application/json">'+payload+'</script><script>'+script+'</script></body>',1)
