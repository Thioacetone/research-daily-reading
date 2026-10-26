"""Classify and deduplicate published papers without changing their content."""
import re
import unicodedata
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from urllib.parse import unquote
from reading_policy import DIRECTIONS as BROAD_DIRECTIONS,identity_keys
from paper_classification import EXTRA_LABELS,reviewed,display_direction

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
DIRECTION_LABELS.update(EXTRA_LABELS)

# Reader navigation uses disciplines; evidence and daily selection keep their
# original scientific subjects so regrouping does not alter publication quotas.
BROWSE_DIRECTIONS={
    'inorganic':'无机化学','organic':'有机化学','physical':'物理化学','computational':'计算化学',
    'analytical':'分析化学','polymer':'高分子化学','materials':'材料化学',
    'chemical-biology':'生物化学','medicinal':'药物化学',
    'environmental':'环境化学','chemical-engineering':'化学工程',
    'interdisciplinary':'交叉学科','other':'其他／待分类',
}
BROWSE_ENGLISH={
    'inorganic':'Inorganic chemistry','organic':'Organic chemistry',
    'physical':'Physical chemistry','computational':'Computational chemistry','analytical':'Analytical chemistry',
    'polymer':'Polymer chemistry','materials':'Materials chemistry',
    'chemical-biology':'Biochemistry','medicinal':'Medicinal chemistry',
    'environmental':'Environmental chemistry','chemical-engineering':'Chemical engineering',
    'interdisciplinary':'Interdisciplinary studies','other':'Subject pending review',
}
DIRECTION_GROUPS={
    'inorganic':'inorganic','nuclear':'inorganic','geochemistry':'inorganic',
    'organic':'organic',
    'physical':'physical','theoretical':'computational','catalysis':'physical',
    'electrochemistry':'physical','energy':'physical','supramolecular':'physical',
    'analytical':'analytical','spatial-proteomics':'analytical',
    'polymer':'polymer','materials':'materials',
    'chemical-biology':'chemical-biology','bioorthogonal':'chemical-biology',
    'chemical-probes':'chemical-biology','protein-degradation':'chemical-biology',
    'structural-biology':'chemical-biology','bioactive-peptides':'chemical-biology',
    'biophysical':'physical',
    'drug-discovery':'medicinal','cadd-aidd':'computational',
    'neuropharmacology':'medicinal','drug-delivery':'medicinal',
    'radiopharmaceuticals':'medicinal',
    'environmental':'environmental','chemical-engineering':'chemical-engineering',
    'interdisciplinary':'interdisciplinary','cheminformatics':'computational',
    'computational-structural-biology':'computational','cancer-biology':'interdisciplinary',
    'medical-education':'interdisciplinary','diagnostic-imaging':'interdisciplinary',
    'microbial-ecology':'interdisciplinary','digital-mental-health':'interdisciplinary',
    'other':'other',
}


def browse_direction(subject):
    return DIRECTION_GROUPS.get(subject,subject if subject in BROWSE_DIRECTIONS else 'other')


def reader_direction(item):
    return browse_direction(paper_direction(item))


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
    verified=reviewed(item)
    if verified:return verified['paper_type']
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
    # Never turn a search keyword or a broad title match into a reviewed label.
    result=display_direction(item)
    return result if result in DIRECTION_LABELS else 'other'


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
    for name in ('reading-content.zip','site-publication.json','reviewed_classifications.json'):
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
                    'type':paper_type(item),'direction':reader_direction(item)}
            records.append(record)
            for alias in identities:by_identity[alias]=record
    return newest_first(records)


def filter_papers(records,kind='all',direction='all'):
    direction=direction if direction=='all' else browse_direction(direction)
    return [record for record in records
            if (kind=='all' or record['type']==kind)
            and (direction=='all' or browse_direction(record['direction'])==direction)]


def category_counts(records,axis,kind='all',direction='all'):
    """Count the other filter's scope; return populated choices by size."""
    if axis=='direction':
        scope=filter_papers(records,kind=kind)
        labels={'all':'全部方向',**BROWSE_DIRECTIONS}
    elif axis=='type':
        scope=filter_papers(records,direction=direction)
        labels=TYPE_LABELS
    else:
        raise ValueError('Unknown category axis')
    rows=[]
    for key,label in labels.items():
        count=len(scope) if key=='all' else sum(
            (browse_direction(record[axis]) if axis=='direction' else record[axis])==key for record in scope)
        if count or key=='all':rows.append({'key':key,'label':label,'count':count})
    return sorted(rows,key=lambda row:(-row['count'],row['key']!='all',row['label']))


def validate_reader_classifications(reports):
    """Refuse a bundle whose published labels cannot be rendered by the reader.

    Includes precomputed issues and all historical reports. A reviewed historical
    out-of-scope paper retains its accurate label, without becoming eligible for
    new recommendations. Raw discovery lanes never satisfy this check.
    """
    missing=[]
    for entry in reports:
        for section in entry['report']['sections'].values():
            for item in section['items']:
                if reader_direction(item)=='other' or paper_type(item) not in ('review','research'):
                    missing.append(paper_key(item))
    if missing:
        raise ValueError('Published papers lack verified reader classifications: '+', '.join(missing))


def reading_period(records, view='today', today=None):
    """Use edition dates, so a bulk website migration is not a new reading issue."""
    today=today or beijing_today()
    date.fromisoformat(today)
    if view=='today':
        return [record for record in records if record['day']==today]
    if view=='archive':
        return [record for record in records if record['day']<today]
    raise ValueError('Unknown reading period')


def page_parameters(view='today', kind='all', direction='all', paper=None, browse=None):
    """Only the reading route and validated filters belong in navigation URLs."""
    view=view if view in ('today','archive') else 'today'
    values={'view':view}
    if view=='archive':
        values['kind']=kind if kind in TYPE_LABELS else 'all'
        values['direction']=(browse_direction(direction) if direction in DIRECTION_LABELS or direction in BROWSE_DIRECTIONS
                             else 'all')
    if paper:
        values['paper']=paper
    elif view=='archive' and browse in ('direction','type'):
        values['browse']=browse
    return values


def selected_paper(records, key, view='today', today=None):
    return next((record for record in reading_period(records,view,today) if record['key']==key),None)


def as_collection(records, view='library', today=None):
    records=newest_first(records)
    return {'collection':True,'count':len(records),'day':max((r['day'] for r in records),default=''),
            'view':view,'today':today or beijing_today(),'paper_updates':[r.get('updated_on','') for r in records],
            'saved_cards':[record['content'] for record in records],
            'report':{'edition':'paper-recommendation','sections':{'library':{'items':[r['item'] for r in records]}}}}
