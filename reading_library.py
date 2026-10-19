"""Read published deep-reading reports without starting mail or model jobs."""
from datetime import date
import json
from pathlib import Path


def load_library(root):
    reports=[]
    unavailable=0
    for file in (Path(root)/'data'/'paper-recommendation').glob('*/report.json'):
        try:
            value=json.loads(file.read_text(encoding='utf-8'))
            if value.get('demo') or value.get('edition')!='paper-recommendation':
                continue
            day=value.get('recommendation_date') or value['date']
            date.fromisoformat(day)
            count=sum(len(section['items']) for section in value['sections'].values())
            if count<1:
                continue
            html_path=file.with_name('report.html')
            if html_path.is_file():
                document=html_path.read_text(encoding='utf-8')
                if '<html' not in document.lower() or '</body>' not in document.lower():
                    raise ValueError('Incomplete reading page')
            else:
                from bilingual_mail import render
                _,document=render(value)
            reports.append({'file':file,'report':value,'day':day,'count':count,'document':document})
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            unavailable+=1
    reports.sort(key=lambda entry:(entry['day'],str(entry['file'])),reverse=True)
    return reports,unavailable
