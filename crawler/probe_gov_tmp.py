import sys, json
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from core.http import HttpClient
http = HttpClient()
params = {
    't': 'zhengcelibrary', 'q': '生产安全事故应急预案管理办法',
    'searchfield': 'title', 'sort': 'score', 'sortType': 1,
    'p': 0, 'n': 10, 'type': 'gwyzcwjk',
}
r = http.get('https://sousuo.www.gov.cn/search-gov/data', params=params)
d = r.json()
sv = d.get('searchVO') or {}
catmap = sv.get('catMap') or {}
rec = catmap['gongbao']['listVO'][0]
print('=== 完整字段 ===')
for k, v in rec.items():
    print(f'  {k}: {str(v)[:80]}')
