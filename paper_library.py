"""Classify and deduplicate published papers without changing their content."""
import re
import unicodedata
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from urllib.parse import unquote
from reading_policy import DIRECTIONS as BROAD_DIRECTIONS,identity_keys

TYPE_LABELS={'all':'全部类型','review':'综述','research':'非综述'}
DIRECTION_LABELS={
    'drug-discovery':'药物发现与作用机制',
    'cadd-aidd':'CADD/AIDD 与计算药物发现',
    'protein-degradation':'靶向蛋白降解',
    'neuropharmacology':'抑郁症与神经药理',
    'bioorthogonal':'生物正交反应',
    'chemical-probes':'化学探针与共价配体',
    'chemical-biology':'化学生物学',
    'other':'其他／待分类',
}
DIRECTION_LABELS.update({key:value for key,value in BROAD_DIRECTIONS.items() if key not in DIRECTION_LABELS})


def saved_cards(entry):
    if 'saved_cards' in entry:
        cards=list(entry['saved_cards'])
    else:
        cards=re.findall(r'<div\b[^>]*class=[\'"]reading-copy[\'"][^>]*>(.*?)</div></td></tr></table>',
                         entry['document'],flags=re.S)
    if len(cards)!=entry['count']:
        raise ValueError('Saved reading page does not contain every article')
    return cards


def paper_type(item):
    value=item.get('recommendation_kind','').casefold()
    if value in ('review','research'):
        return value
    label=item.get('kind','').strip().casefold()
    if label in ('综述','review','review article','systematic review','meta-analysis'):
        return 'review'
    if label in ('研究论文','研究性文章','research','research article','article'):
        return 'research'
    return 'other'


def paper_direction(item):
    declared=item.get('research_direction')
    if declared in DIRECTION_LABELS:
        return declared
    # Infer only from the paper's own title, not speculative future applications.
    title=(item.get('paper_title') or item.get('title') or '').casefold()
    for direction,pattern in (
        ('bioorthogonal',r'bioorthogonal|bio-orthogonal|staudinger ligation|click-to-release|tetrazine'),
        ('cadd-aidd',r'docking|virtual screening|computer.aided|deep learning|generative|swissadme'),
        ('neuropharmacology',r'psychedelic|psychoplastogen|hallucinogen|antidepressant|neural plasticity|depression'),
        ('protein-degradation',r'degrad|protac|lytac'),
        ('chemical-probes',r'covalent ligand|chemical probe|chemoproteom'),
        ('drug-discovery',r'drug discovery|drug design'),
        ('chemical-biology',r'chemical biology')):
        if re.search(pattern,title):
            return direction
    return 'other'


def paper_key(item):
    doi=unquote(str(item.get('doi') or '')).strip().casefold()
    doi=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',doi)
    if doi:
        return 'doi:'+doi
    title=item.get('paper_title') or item.get('title') or item.get('title_zh') or ''
    title=' '.join(unicodedata.normalize('NFKC',title).casefold().split())
    if not title:
        raise ValueError('Paper has neither DOI nor title')
    return 'title:'+title


def beijing_today():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def published_signature(root,today=None):
    stamps=[]
    for name in ('reading-content.zip','site-publication.json'):
        try:
            info=(Path(root)/name).stat();stamps.append((info.st_mtime_ns,info.st_size))
        except OSError:stamps.append((0,0))
    return (today or beijing_today(),tuple(stamps))


def publication_history(records, previous, published_on=None):
    """Persist website dates at publication, never on a reader's page refresh."""
    published_on=published_on or beijing_today()
    date.fromisoformat(published_on)
    history={}
    for record in records:
        fingerprint=hashlib.sha256(record['content'].encode('utf-8')).hexdigest()
        old=previous.get(record['key'],{})
        updated_on=old.get('updated_on') if old.get('content_sha256')==fingerprint else published_on
        date.fromisoformat(updated_on)
        history[record['key']]={'updated_on':updated_on,'content_sha256':fingerprint}
    return history


def newest_first(records, today=None):
    today=today or beijing_today()
    return sorted(records,key=lambda r:(r.get('updated_on')==today,
                  r.get('updated_on',''),r['day']),reverse=True)


def build_paper_library(reports, history=None):
    records=[];by_identity={}
    for entry in sorted(reports,key=lambda entry:(entry['day'],str(entry.get('file',''))),reverse=True):
        items=[item for section in entry['report']['sections'].values() for item in section['items']]
        for item,content in zip(items,saved_cards(entry)):
            key=paper_key(item)
            identities=identity_keys(item)
            matched=next((by_identity[k] for k in identities if k in by_identity),None)
            if matched is not None:
                # Keep the newest corrected copy, but never promote an old paper
                # into a new day's recommendations by publishing it again.
                matched['day']=min(matched['day'],entry['day'])
                for alias in identities:by_identity[alias]=matched
                continue
            updated_on=(history or {}).get(key,{}).get('updated_on','')
            if updated_on:
                date.fromisoformat(updated_on)
            record={'key':key,'item':item,'content':content,'day':entry['day'],'updated_on':updated_on,
                    'type':paper_type(item),'direction':paper_direction(item)}
            records.append(record)
            for alias in identities:by_identity[alias]=record
    return newest_first(records)


def filter_papers(records,kind='all',direction='all'):
    return [record for record in records
            if (kind=='all' or record['type']==kind)
            and (direction=='all' or record['direction']==direction)]


def reading_period(records, view='today', today=None):
    """Use edition dates, so a bulk website migration is not a new reading issue."""
    today=today or beijing_today()
    date.fromisoformat(today)
    if view=='today':
        return [record for record in records if record['day']==today]
    if view=='archive':
        return [record for record in records if record['day']<today]
    raise ValueError('Unknown reading period')


def page_parameters(view='today', kind='all', direction='all', paper=None):
    """Only the reading route and validated filters belong in navigation URLs."""
    view=view if view in ('today','archive') else 'today'
    values={'view':view}
    if view=='archive':
        values['kind']=kind if kind in TYPE_LABELS else 'all'
        values['direction']=direction if direction in DIRECTION_LABELS or direction=='all' else 'all'
    if paper:
        values['paper']=paper
    return values


def selected_paper(records, key, view='today', today=None):
    return next((record for record in reading_period(records,view,today) if record['key']==key),None)


def as_collection(records, view='library', today=None):
    records=newest_first(records)
    return {'collection':True,'count':len(records),'day':max((r['day'] for r in records),default=''),
            'view':view,'today':today or beijing_today(),'paper_updates':[r.get('updated_on','') for r in records],
            'saved_cards':[record['content'] for record in records],
            'report':{'edition':'paper-recommendation','sections':{'library':{'items':[r['item'] for r in records]}}}}
