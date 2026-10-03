from __future__ import annotations
from difflib import SequenceMatcher
from dataclasses import dataclass
from intelligence.news.models import NewsItem

@dataclass(frozen=True)
class StoryCluster:
    cluster_id:str; news_ids:tuple[str,...]; source_count:int

def cluster_news(items:list[NewsItem],threshold:float=0.78)->list[StoryCluster]:
    groups=[]
    for item in sorted(items,key=lambda x:x.published_at):
        target=None; best=0
        for i,g in enumerate(groups):
            for other in g:
                score=SequenceMatcher(None,item.headline.lower(),other.headline.lower(),autojunk=False).ratio()
                if score>best: best=score; target=i
        if target is not None and best>=threshold: groups[target].append(item)
        else: groups.append([item])
    return [StoryCluster(cluster_id=f"story-{i+1:04d}",news_ids=tuple(x.news_id for x in g),source_count=len({x.source for x in g})) for i,g in enumerate(groups)]
