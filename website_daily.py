"""Cloud-only daily website build; no email credentials or inference API calls."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import urllib.parse
from xml.etree import ElementTree as ET

from reading_policy import (DIRECTIONS,PRIORITY,QUERIES,POLICY_VERSION,PolicyError,
                           choose_daily,validate_daily,identity_keys,direction)
from cloud_bundle import ensure_bundled_files
from reading_library import load_library

ROOT=Path(__file__).resolve().parent
BJ=timezone(timedelta(hours=8))
LOG=logging.getLogger('website-reading')


def history(root):
    ensure_bundled_files(root)
    reports,failed=load_library(root)
    if failed:raise PolicyError('Some historical reports cannot be read; refusing to guess duplicate history')
    path=Path(root)/'reading-history.json'
    saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(saved,dict):raise PolicyError('Website reading history is invalid')
    for entry in reports:
        for section in entry['report']['sections'].values():
            for item in section['items']:
                for key in identity_keys(item):saved[key]=min(saved.get(key,entry['day']),entry['day'])
    for key,day in saved.items():
        if not key.startswith(('doi:','title:')):raise PolicyError('Unknown identity in website history')
        date.fromisoformat(day)
    return reports,saved


def quality(item):
    from paper_classification import classification_ready
    if not classification_ready(item):return False
    from recommendation_sources import EDITORIAL_EXCLUSIONS
    if str(item.get('doi','')).lower() in EDITORIAL_EXCLUSIONS:return False
    from paper_recommendation import complete_item
    from bilingual_mail import complete,VERSION,LAYOUT_VERSION
    return complete_item(item) and complete({'edition':'paper-recommendation','bilingual_version':VERSION,
                    'bilingual_layout':LAYOUT_VERSION,'sections':{'papers':{'items':[item]}}})


def candidate_bank(root,used):
    path=Path(root)/'reading-candidates.json'
    if not path.exists():return []
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('policy_version')!=POLICY_VERSION:return []
    selected=[];seen=set(used)
    for item in value.get('items',[]):
        keys=identity_keys(item)
        if keys&seen or not quality(item):continue
        selected.append(item);seen.update(keys)
    return selected


def collect_candidates(root,pools):
    """Save completed reviews even if another lane fails; publication alone uses them up."""
    _,saved=history(root)
    items=candidate_bank(root,set(saved));seen=set(saved)
    for item in items:seen.update(identity_keys(item))
    held_pool=[]
    rejection_path=Path(root)/'reading-candidates.json'
    previous=json.loads(rejection_path.read_text(encoding='utf-8')) if rejection_path.exists() else {}
    rejections=previous.get('rejections',{})
    today=datetime.now(BJ).date().isoformat()
    rejections={k:v for k,v in rejections.items() if v.get('until','')>today}
    for path in sorted(Path(pools).rglob('*.json')):
        value=json.loads(path.read_text(encoding='utf-8'))
        rejections.update(value.get('rejections',{}))
        for item in value.get('items',[]):
            keys=identity_keys(item)
            if keys&seen:continue
            if not quality(item):
                held_pool.append(item)
                continue
            items.append(item);seen.update(keys)
    destination=Path(root)/'reading-candidates.json'
    # Keep completed older reviews for reclassification; never count them as
    # qualified, and never discard their editorial work when rules change.
    held=[]
    if destination.exists():
        previous=json.loads(destination.read_text(encoding='utf-8'))
        for item in previous.get('items',[]):
            keys=identity_keys(item)
            if keys&seen:continue
            held.append(item);seen.update(keys)
    for item in held_pool:
        keys=identity_keys(item)
        if keys&seen:continue
        held.append(item);seen.update(keys)
    temporary=destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'policy_version':POLICY_VERSION,'items':items+held,
                                    'rejections':rejections},ensure_ascii=False),encoding='utf-8')
    temporary.replace(destination)
    print(json.dumps({'unused_completed_reviews':len(items),'held_for_reclassification':len(held)}))


def already_published(root,day):
    reports,saved=history(root)
    used={key for key,first in saved.items() if first!=day}
    for entry in reports:
        if entry['day']!=day or entry['report'].get('reading_policy_version')!=POLICY_VERSION:continue
        items=[i for s in entry['report']['sections'].values() for i in s['items']]
        # Issued editions are immutable: correcting their labels must not repost
        # old papers or erase deduplication history. New publications use quality.
        # Legacy issues have a successful, saved 10/5/3 selection audit, but that
        # audit is not reused as evidence of a paper's scientific subject.
        audit=entry['report'].get('selection_audit',{})
        from paper_classification import reviewed
        if (len(items)==10 and audit.get('papers')==10 and audit.get('policy_version')==POLICY_VERSION
                and all(reviewed(i) is not None for i in items)
                and all(not identity_keys(i)&used for i in items)
                and len({next(k for k in identity_keys(i) if k.startswith('doi:'))
                         for i in items if i.get('doi')})==10):return True
        try:validate_daily(items,used,quality)
        except PolicyError:continue
        return True
    return False


def preflight_state(root,day):
    ready=already_published(root,day)
    generate=False;lanes=[];counts=Counter()
    if not ready:
        _,saved=history(root)
        bank=candidate_bank(root,set(saved))
        counts.update(direction(i) for i in bank)
        try:choose_daily(bank,set(saved),quality_check=quality)
        except PolicyError:
            generate=True
            capacity=sum(min(3,n) for n in counts.values())
            priority=sum(min(3,counts[k]) for k in PRIORITY)
            # Fix the binding quota first. Never rerun already-sufficient broad
            # lanes while the whole issue is blocked by one missing priority.
            lanes=[k for k in DIRECTIONS if k in PRIORITY and counts[k]<3] if priority<5 else []
            if capacity<10:
                broad=[k for k in DIRECTIONS if k not in PRIORITY and counts[k]<2]
                broad.sort(key=lambda k:(counts[k],hashlib.sha256((day+k).encode()).digest()))
                lanes+=broad[:max(1,6-len(lanes))]
    return {'day':day,'run':str(not ready).lower(),'generate':str(generate).lower(),
            'lanes':json.dumps(lanes),'available':sum(counts.values()),
            'priority_available':sum(min(3,counts[k]) for k in PRIORITY)}


def automatic_day(root,today=None,horizon=2):
    """Repair today first, then prepare two days ahead; never abandon a gap."""
    current=today or datetime.now(BJ).date()
    for offset in range(horizon+1):
        day=(current+timedelta(days=offset)).isoformat()
        if not already_published(root,day):return day
    return (current+timedelta(days=horizon)).isoformat()


def requested_day(value=None,next_day=False,today=None):
    if value and next_day:raise PolicyError('Choose either an explicit date or next day')
    current=today or datetime.now(BJ).date()
    return date.fromisoformat(value).isoformat() if value else (current+timedelta(days=int(next_day))).isoformat()


def discover(root,lane,used,day,audit=None):
    """Search broad themes in independent indexes; only vetted journals enter the pool."""
    from recommendation_sources import read_json,interleave,is_preprint,BAD_TITLE,EPMC,discover_pubmed,title_abstract_query
    from journal_discovery import JournalRegistry
    from crossref_metadata import normalize_doi
    from recommendation_sources import EDITORIAL_EXCLUSIONS
    used=set(used)|{'doi:'+doi for doi in EDITORIAL_EXCLUSIONS}
    registry=JournalRegistry.load(root)
    audit={} if audit is None else audit
    for name in ('Europe PMC','Crossref','PubMed'):
        audit[name]={'queries':0,'failures':0}
    lanes=[]
    query=QUERIES[lane]
    for sort in ('sort_cited:y','sort_date:y'):
        found=[];cursor='*'
        for _ in range(3):
            args={'query':f'{title_abstract_query(query)} AND OPEN_ACCESS:Y AND HAS_FT:Y AND FIRST_PDATE:[1900-01-01 TO {day}] {sort}',
                  'format':'json','resultType':'core','pageSize':50,'cursorMark':cursor}
            audit['Europe PMC']['queries']+=1
            try:result=read_json(EPMC+'search?'+urllib.parse.urlencode(args))
            except (OSError,ValueError):
                audit['Europe PMC']['failures']+=1
                break
            rows=result.get('resultList',{}).get('result',[])
            for row in rows:
                doi=normalize_doi(row.get('doi'));title=row.get('title','')
                journal=row.get('journalInfo',{}).get('journal',{}).get('title','') or row.get('journalTitle','')
                item={'doi':doi,'title':title}
                if (not doi or identity_keys(item)&used or is_preprint(doi) or BAD_TITLE.search(title)
                        or row.get('isRetracted')=='Y' or not registry.match(journal)):
                    continue
                found.append({**item,'pmcid':row.get('pmcid',''),'candidate_journal':journal,
                              'discovery_sources':['Europe PMC'],'research_direction':lane})
            nxt=result.get('nextCursorMark')
            if len(found)>=12 or not rows or not nxt or nxt==cursor:break
            cursor=nxt
        lanes.append(found)
    for sort in ('is-referenced-by-count','relevance'):
        found=[]
        for offset in (0,60,120):
            args={'query.title':query.replace(' OR ',' ').replace(' AND ',' '),
                  'filter':f'type:journal-article,until-pub-date:{day}','rows':60,'offset':offset,
                  'sort':sort,'order':'desc'}
            audit['Crossref']['queries']+=1
            try:rows=read_json('https://api.crossref.org/works?'+urllib.parse.urlencode(args))['message']['items']
            except (OSError,ValueError,KeyError):
                audit['Crossref']['failures']+=1
                break
            for row in rows:
                doi=normalize_doi(row.get('DOI'));title=' '.join(row.get('title') or [])
                journals=row.get('container-title') or []
                item={'doi':doi,'title':title}
                if (not doi or identity_keys(item)&used or is_preprint(doi) or BAD_TITLE.search(title)
                        or not any(registry.match(j,row.get('ISSN',[])) for j in journals)
                        or any(u.get('type') in ('retraction','withdrawal','expression-of-concern') for u in row.get('update-to',[]))
                        or any(row.get('relation',{}).get(k) for k in ('is-retracted-by','is-preprint-of'))):continue
                found.append({**item,'pmcid':'','candidate_journal':journals[0],
                              'discovery_sources':['Crossref'],'research_direction':lane})
            if len(found)>=12 or len(rows)<60:break
        lanes.append(found)
    used_dois={key[4:] for key in used if key.startswith('doi:')}
    for kind in ('research','review'):
        lanes.append(discover_pubmed(kind,used_dois,date.fromisoformat(day),themes=((lane,title_abstract_query(query,'pubmed')),),registry=registry,audit=audit['PubMed']))
    return interleave(lanes)


def prepare_item(root,item,day,writer=None):
    if quality(item):return item
    from paper_classification import classification_ready
    if not classification_ready(item):
        # Old bilingual/editorial caches predate subject review. Re-read the
        # original rather than letting an otherwise complete cache bypass it.
        from paper_recommendation import load_candidate_fulltext
        from recommendation_writer import DeepReadingWriter
        paper,paragraphs,abstract=load_candidate_fulltext(root,item)
        writer=writer or DeepReadingWriter(root)
        item=writer.analyze(paper,paragraphs,abstract)
        if not item or not classification_ready(item):raise PolicyError('Original subject classification requires review')
    import bilingual_mail
    report={'date':(date.fromisoformat(day)-timedelta(days=1)).isoformat(),
            'recommendation_date':day,'edition':'paper-recommendation',
            'sections':{'papers':{'status':'ok','items':[item],'note':'','sources':[]}}}
    translator=bilingual_mail.LocalTranslator(root)
    if writer is not None:translator.writer=writer
    bilingual_mail.prepare(report,root,translator=translator)
    if not quality(item):raise PolicyError('Full text, affiliations or paragraph translations are incomplete')
    return item


def worker(root,lane,day,output):
    from paper_recommendation import load_catalog,load_candidate_fulltext,complete_item,RecommendationError
    from recommendation_writer import DeepReadingWriter
    from journal_discovery import JournalRegistry
    reports,saved=history(root);used=set(saved)
    # Existing stock is available to the assembler, not a fresh discovery by
    # every worker. Recounting it here made all subsequent retries stall.
    for item in candidate_bank(root,used):used.update(identity_keys(item))
    bank_path=Path(root)/'reading-candidates.json'
    state=json.loads(bank_path.read_text(encoding='utf-8')) if bank_path.exists() else {}
    for key,row in state.get('rejections',{}).items():
        if row.get('until','')>datetime.now(BJ).date().isoformat():used.add(key)
    registry=JournalRegistry.load(root)
    result=[];writer=DeepReadingWriter(root)
    diagnostics={'discovered':0,'fulltext_failed':0,'journal_rejected':0,
                 'editorial_rejected':0,'bilingual_failed':0,'qualified':0,
                 'examined':0,'editorial_attempts':0,'rejection_reasons':{}}
    def reason(value):
        reasons=diagnostics['rejection_reasons']
        reasons[value]=reasons.get(value,0)+1
    target=2 if lane in PRIORITY else 1
    rejected={}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    def checkpoint():
        diagnostics['qualified']=len(result)
        temporary=output.with_suffix('.tmp')
        temporary.write_text(json.dumps({'day':day,'lane':lane,'items':result,
                             'diagnostics':diagnostics,'rejections':rejected},ensure_ascii=False),encoding='utf-8')
        temporary.replace(output)
    def reject_candidate(candidate,why):
        rejected.update({k:{'until':(datetime.now(BJ).date()+timedelta(days=3)).isoformat(),
                               'reason':why} for k in identity_keys(candidate) if k.startswith('doi:')})
        checkpoint()
    def enough():
        # Cross-lane successes are retained, but a broad discovery must not
        # terminate a worker whose purpose is to fill a priority-area deficit.
        return sum(direction(i)==lane for i in result)>=target or len(result)>=6
    checkpoint()
    curated=[i for i in load_catalog(root) if direction(i)==lane and not identity_keys(i)&used]
    for item in curated:
        if identity_keys(item)&used:continue
        if not registry.match(item.get('venue','')):continue
        try:item=prepare_item(root,json.loads(json.dumps(item)),day,writer)
        except (OSError,ValueError):
            diagnostics['bilingual_failed']+=1
            continue
        result.append(item);used.update(identity_keys(item));checkpoint()
        if enough():break
    if not enough():
        source_audit={}
        candidates=discover(root,lane,used,day,audit=source_audit)
        diagnostics['sources']=source_audit
        diagnostics['discovered']=len(candidates)
        # Unavailable metadata must not consume the full-text editorial budget.
        # Prefer identity-resolved bodies, while keeping other discoveries as fallback.
        from recommendation_sources import plos_fulltext_url
        candidates=sorted(candidates,key=lambda c:not (c.get('pmcid') or plos_fulltext_url(c['doi'])))
        for candidate in candidates[:48]:
            if diagnostics['editorial_attempts']>=12:break
            if identity_keys(candidate)&used:continue
            diagnostics['examined']+=1
            stage='fulltext_failed'
            try:
                paper,paragraphs,abstract=load_candidate_fulltext(root,candidate)
                if not registry.match(paper.get('venue','')):
                    diagnostics['journal_rejected']+=1
                    continue
                from affiliation_sources import units_complete,supplement_affiliations
                if not units_complete(paper):supplement_affiliations(paper,root)
                if not units_complete(paper):
                    diagnostics['editorial_rejected']+=1;reason('affiliation_detail_or_country')
                    reject_candidate(candidate,'affiliation_detail_or_country')
                    continue
                stage='editorial_rejected'
                diagnostics['editorial_attempts']+=1
                item=writer.analyze(paper,paragraphs,abstract)
                # Keep valid interdisciplinary discoveries. The final selector
                # applies quotas to the full-text judgement, never this search lane.
                if not item or not complete_item(item) or direction(item) not in DIRECTIONS:
                    diagnostics['editorial_rejected']+=1
                    rejection=str(getattr(writer,'last_rejection','') or 'final_item_check')
                    reason(rejection)
                    LOG.info('Candidate rejected: %s (%s)',candidate['doi'],rejection)
                    reject_candidate(candidate,rejection)
                    continue
                stage='bilingual_failed'
                item=prepare_item(root,item,day,writer)
            except (OSError,ValueError,ET.ParseError,RecommendationError) as exc:
                diagnostics[stage]+=1
                detail=type(exc).__name__
                if str(exc)=='Full-text evidence exceeds the model context budget':detail='model_context_budget'
                reason(stage+':'+detail)
                LOG.warning('Candidate did not pass full-text or bilingual checks: %s',candidate['doi'])
                reject_candidate(candidate,stage+':'+detail)
                continue
            result.append(item);used.update(identity_keys(item));checkpoint()
            if enough():break
    checkpoint()
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        summary=[f'### {lane}',f'- Date: {day}',
                 *[f'- {key}: {value}' for key,value in diagnostics.items()],
                 *[f"- Qualified: `{item['doi']}` ({direction(item)})" for item in result]]
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as stream:
            stream.write('\n'.join(summary)+'\n')
    print(json.dumps({'lane':lane,'qualified_papers':len(result)}))


def combine(root,day,pools):
    import bilingual_mail
    from paper_library import saved_cards
    reports,saved=history(root)
    if already_published(root,day):
        print('A complete non-repeating issue is already published; unchanged.');return
    candidates=candidate_bank(root,set(saved))
    for path in sorted(Path(pools).rglob('*.json')):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('day')==day:candidates.extend(value.get('items',[]))
    chosen=choose_daily(candidates,set(saved),quality_check=quality)
    audit=validate_daily(chosen,set(saved),quality)
    sources=[]
    for index,item in enumerate(chosen,1):
        sid='s'+str(index)
        item.update(source_ids=[sid],primary_source_id=sid)
        sources.append({'id':sid,'title':'Verified original paper','url':'https://doi.org/'+item['doi']})
    report={'date':(date.fromisoformat(day)-timedelta(days=1)).isoformat(),'recommendation_date':day,
            'generated_at':datetime.now(BJ).isoformat(),'edition':'paper-recommendation','demo':False,
            'reading_policy_version':POLICY_VERSION,'selection_audit':audit,
            'bilingual_version':bilingual_mail.VERSION,'bilingual_layout':bilingual_mail.LAYOUT_VERSION,
            'sections':{'papers':{'status':'ok','items':chosen,'sources':sources,'note':''}}}
    if not bilingual_mail.complete(report):raise PolicyError('Bilingual report is incomplete')
    plain,document=bilingual_mail.render(report)
    saved_cards({'document':document,'count':10})
    destination=Path(root)/'data/paper-recommendation'/report['date']
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'report.html').write_text(document,encoding='utf-8')
    (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for item in chosen:
        for key in identity_keys(item):saved.setdefault(key,day)
    (Path(root)/'reading-history.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        lines=[f'## Published daily reading: {day}',
               f'- Validated papers: {audit["papers"]}',f'- Priority-area papers: {audit["priority_papers"]}',
               '- Deduplicated against the complete publication history.',
               '- Every main direction contains at most three papers.','']
        for index,item in enumerate(chosen,1):
            title=' '.join(str(item.get('title_zh') or item['paper_title']).split())
            lines.append(f'{index}. {title} — `{item["doi"]}`')
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
    print(json.dumps(audit,ensure_ascii=False))


def release_window(root,pools,today=None,horizon=2):
    """Publish every available issue in date order, preserving prior editions."""
    current=today or datetime.now(BJ).date();published=[];pending=None
    for offset in range(horizon+1):
        day=(current+timedelta(days=offset)).isoformat()
        if already_published(root,day):continue
        try:combine(root,day,pools)
        except PolicyError:
            pending=preflight_state(root,day);break
        published.append(day)
    status={'checked_at':datetime.now(BJ).isoformat(),'today':current.isoformat(),
            'today_ready':already_published(root,current.isoformat()),
            'published_now':published,'next_pending':pending}
    (Path(root)/'reading-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False))
    return status


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('preflight','worker','collect','combine','release'))
    p.add_argument('--date')
    p.add_argument('--next-day',action='store_true')
    p.add_argument('--lane',choices=list(DIRECTIONS));p.add_argument('--output',default='pool/result.json')
    p.add_argument('--pools',default='pool');args=p.parse_args()
    if args.next_day and args.mode!='preflight':p.error('--next-day is only used by preflight')
    args.date=(automatic_day(ROOT) if args.mode=='preflight' and not args.date and not args.next_day
               else requested_day(args.date,args.next_day))
    if args.mode=='preflight':
        if not datetime.now(BJ).date()<=date.fromisoformat(args.date)<=datetime.now(BJ).date()+timedelta(days=2):
            p.error('Only today or the next two days can be generated automatically')
        values=preflight_state(ROOT,args.date)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
                for key,value in values.items():f.write(key+'='+str(value)+'\n')
        print(json.dumps(values))
    elif args.mode=='worker':
        if not args.lane:p.error('--lane is required')
        worker(ROOT,args.lane,args.date,args.output)
    elif args.mode=='collect':collect_candidates(ROOT,args.pools)
    elif args.mode=='release':
        status=release_window(ROOT,args.pools)
        target_ready=already_published(ROOT,args.date)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
                f.write('published='+str(bool(status['published_now'])).lower()+'\n')
                f.write('target_ready='+str(target_ready).lower()+'\n')
        if not target_ready:raise PolicyError('Requested issue is incomplete; saved candidates will be retried automatically')
    else:combine(ROOT,args.date,args.pools)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    main()
