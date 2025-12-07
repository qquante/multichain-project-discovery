# tweets/query_builder.py
from typing import List, Optional
import hashlib


class QueryBuilder:
    
    def __init__(self):
        self._parts: List[str] = []
        self._keywords: List[str] = []
        self._from_users: List[str] = []
        self._exclude_replies: bool = False
        self._exclude_retweets: bool = False
        self._exclude_quotes: bool = False
        self._min_likes: Optional[int] = None
        self._min_retweets: Optional[int] = None
        self._min_replies: Optional[int] = None
        self._since: Optional[str] = None
        self._until: Optional[str] = None
        self._lang: Optional[str] = None
        self._has_media: bool = False
        self._has_links: bool = False
        self._verified_only: bool = False
        self._blue_verified_only: bool = False
    
    def keywords(self, *words: str) -> 'QueryBuilder':
        self._keywords.extend(words)
        return self
    
    def keyword_phrases(self, *phrases: str) -> 'QueryBuilder':
        for phrase in phrases:
            self._keywords.append(f'"{phrase}"')
        return self
    
    def from_user(self, username: str) -> 'QueryBuilder':
        self._from_users.append(f"from:{username}")
        return self
    
    def exclude_replies(self) -> 'QueryBuilder':
        self._exclude_replies = True
        return self
    
    def exclude_retweets(self) -> 'QueryBuilder':
        self._exclude_retweets = True
        return self
    
    def exclude_quotes(self) -> 'QueryBuilder':
        self._exclude_quotes = True
        return self
    
    def min_likes(self, count: int) -> 'QueryBuilder':
        self._min_likes = count
        return self
    
    def min_retweets(self, count: int) -> 'QueryBuilder':
        self._min_retweets = count
        return self
    
    def min_replies(self, count: int) -> 'QueryBuilder':
        self._min_replies = count
        return self
    
    def since(self, date: str) -> 'QueryBuilder':
        self._since = date
        return self
    
    def until(self, date: str) -> 'QueryBuilder':
        self._until = date
        return self
    
    def language(self, lang_code: str) -> 'QueryBuilder':
        self._lang = lang_code
        return self
    
    def has_media(self) -> 'QueryBuilder':
        self._has_media = True
        return self
    
    def has_links(self) -> 'QueryBuilder':
        self._has_links = True
        return self
    
    def verified_only(self) -> 'QueryBuilder':
        self._verified_only = True
        return self
    
    def blue_verified_only(self) -> 'QueryBuilder':
        self._blue_verified_only = True
        return self
    
    def raw(self, query_part: str) -> 'QueryBuilder':
        self._parts.append(query_part)
        return self
    
    def build(self) -> str:
        parts = []
        
        if self._keywords:
            if len(self._keywords) == 1:
                parts.append(self._keywords[0])
            else:
                parts.append(f"({' OR '.join(self._keywords)})")
        
        if self._from_users:
            if len(self._from_users) == 1:
                parts.append(self._from_users[0])
            else:
                parts.append(f"({' OR '.join(self._from_users)})")
        
        if self._exclude_replies:
            parts.append("-filter:replies")
        if self._exclude_retweets:
            parts.append("-filter:retweets")
        if self._exclude_quotes:
            parts.append("-filter:quote")
        if self._min_likes:
            parts.append(f"min_faves:{self._min_likes}")
        if self._min_retweets:
            parts.append(f"min_retweets:{self._min_retweets}")
        if self._min_replies:
            parts.append(f"min_replies:{self._min_replies}")
        if self._since:
            parts.append(f"since:{self._since}")
        if self._until:
            parts.append(f"until:{self._until}")
        if self._lang:
            parts.append(f"lang:{self._lang}")
        if self._has_media:
            parts.append("filter:media")
        if self._has_links:
            parts.append("filter:links")
        if self._verified_only:
            parts.append("filter:verified")
        if self._blue_verified_only:
            parts.append("filter:blue_verified")
        
        parts.extend(self._parts)
        return " ".join(parts)
    
    def get_hash(self) -> str:
        return hashlib.md5(self.build().encode()).hexdigest()[:16]
    
    def __str__(self) -> str:
        return self.build()


def early_project_query() -> QueryBuilder:
    return (
        QueryBuilder()
        .keyword_phrases(
            "not live yet",
            "not deployed",
            "no ca yet",
            "no CA yet",
            "live soon",
            "launching soon",
            "launch soon",
            "coming soon",
            "minting soon",
            "mint soon",
            "stealth launch",
            "fair launch soon"
        )
        .exclude_replies()
        .exclude_retweets()
        .language("en")
    )


def crypto_launch_query() -> QueryBuilder:
    return (
        QueryBuilder()
        .keyword_phrases(
            "launching on pump.fun",
            "launching on pumpfun", 
            "stealth launch",
            "fair launch",
            "no presale",
            "contract renounced"
        )
        .exclude_replies()
        .exclude_retweets()
    )


def custom_keywords_query(*keywords: str) -> QueryBuilder:
    return (
        QueryBuilder()
        .keyword_phrases(*keywords)
        .exclude_replies()
        .exclude_retweets()
    )
