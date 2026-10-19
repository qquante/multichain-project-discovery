"""Test AlphaGate API"""
import requests
import json

url = 'https://api.alphagate.io/api/v1/child/discover'
params = {
    'ontop': 'true',
    'page': 1,
    'limit': 5,
    'unfiltered': 'false',
    'exclude_tags[]': 'Launched',
    'order': '-1',
    'min_followers': 0,
    'max_followers': 600000,
    'min_key_followers': 0,
    'max_key_followers': 5000
}
headers = {
    'accept': 'application/json',
    'origin': 'https://alphagate.io',
    'referer': 'https://alphagate.io/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0.0.0'
}
cookies = {
    'userId': '[REMOVED_CREDENTIAL]'
}

try:
    r = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=10)
    print(f'Status: {r.status_code}')
    data = r.json()
    print(f'Message: {data.get("message")}')
    children = data.get('data', {}).get('children', [])
    print(f'Total children: {len(children)}')
    print()
    for i, c in enumerate(children[:5], 1):
        username = c.get('username', 'N/A')
        name = c.get('name', 'N/A')
        followers = c.get('followers_count', 0)
        key_followers = c.get('key_followers_count', 0)
        tags = c.get('tag', [])
        chain = c.get('chain', [])
        bio = (c.get('description') or '')[:80]
        contracts = c.get('contracts', [])
        
        print(f'[{i}] @{username} | {name}')
        print(f'    Followers: {followers} | Key: {key_followers}')
        print(f'    Tags: {tags} | Chain: {chain}')
        print(f'    Bio: {bio}...')
        print(f'    Contracts: {contracts}')
        print()
except Exception as e:
    print(f'Error: {e}')

