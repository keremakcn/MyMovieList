"""Regenerate synthetic parity cases from the authoritative native algorithm."""
import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import random
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
args=parser.parse_args()
sys.path.insert(0,str(args.root))
spec=importlib.util.spec_from_file_location('native_recommendation_model',args.root/'recommendation_model.py')
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026,10,12)
model.date=FixedDate
rng=random.Random(3700)
genres=list(model.GENRES)
def movie(mid):
    year=rng.choice([1975,1989,1999,2005,2014,2023,2025,2026])
    return {'id':mid,'tmdb_id':mid,'title':f'Synthetic film {mid}', 'release_date':f'{year}-02-01',
        'vote_average':rng.choice([5.8,6.5,7.4,8.2,9.0]),'vote_count':rng.choice([30,100,200,1000,5000,15000]),
        'genre_ids':rng.sample(genres,rng.choice([1,2,3])), 'original_language':rng.choice(['en','tr','fr','ja']),
        'keyword_ids':rng.sample(range(100,110),rng.choice([0,1,3])),
        'collection_id':rng.choice([None,None,mid//8]),
        'entities':{'directors':[{'id':500+mid%7}], 'cast':[{'id':600+(mid+i)%12,'popularity':rng.choice([2,20,100])} for i in range(8)]}}
library=[]
for n in range(36):
    item=movie(n+1)
    item.update(rating=rng.choice([None,2,4,6,8,9,10]),favorite=n%5==0,survey_liked=n%6==0)
    library.append(item)
candidates=[movie(n+1000) for n in range(72)]
candidates += [dict(candidates[0]),dict(movie(2000),adult=True),dict(movie(2001),release_date='2027-01-01'),
               dict(movie(2002),release_date='2026-02-30'),dict(movie(2003),title=None)]
legacy=[{'tmdb_id':3,'title':'Legacy one','rating':9,'favorite':False,'genre':'Comedy, Drama', 'director':'Straße', 'year':1975},
        {'tmdb_id':4,'title':'Legacy two','rating':2,'favorite':False,'genre':'Comedy','director':'Straße','year':1989}]
cases=[]
for label,rows in [('empty',[]),('one',library[:1]),('few',library[:4]),('mixed',library),
                  ('negative',[dict(m,rating=2,favorite=False) for m in library]),
                  ('positive',[dict(m,rating=9) for m in library]),('legacy',legacy)]:
    profile=model.build_profile(rows)
    diagnostic={'confidence':profile['confidence'],'count':profile['count'],'ready':profile['ready'],'baseline':profile['baseline'],
                'features':{g:{str(k):v for k,v in values.items()} for g,values in profile['features'].items()}}
    for mode in model.POLICIES:
        for seed in ['', 'parity-seed']:
            ranked=model.rank_candidates(candidates,profile,[1000,1001],mode,10,[1002,1003,1004],seed)
            cases.append({'name':f'{label}-{mode}-{seed or "stable"}','library':rows,'candidates':candidates,
                'options':{'excluded':[1000,1001],'mode':mode,'previous':[1002,1003,1004],'seed':seed,'today':'2026-10-12'},
                'profile':diagnostic,'ranked':[{'id':m['tmdb_id'],'highlight':m['recommendation_highlight']} for m in ranked]})
out=Path(__file__).with_name('recommendation-parity.json')
out.write_text(json.dumps({'native_algorithm':model.ALGORITHM_VERSION,'cases':cases},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(f'{len(cases)} recommendation parity cases generated from native v{model.ALGORITHM_VERSION}.')
