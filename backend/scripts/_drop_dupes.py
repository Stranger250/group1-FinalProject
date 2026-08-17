# -*- coding: utf-8 -*-
"""实验 #3：删除 3 组重复文档（每组保留第一个版本）——语料数据修复。

重复文档（内容逐块 100% 相同，爬虫重复抓取）：
  1. 阿拉善 2·22：删除「内蒙古阿拉善新井煤业露天煤矿…」（保留「…有限公司…」版）
  2. 富洋 6·21：删除「6•21」（半角点）版（保留「6·21」全角点版）
  3. 凯信达 11·21：删除无空格版（保留带空格版）
删除方式：Chroma 按 doc_id 删除 + MySQL knowledge_document 行删除（保持一致）。
"""
import sys, io, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import chromadb
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import SessionLocal

s = get_settings()
client = chromadb.PersistentClient(path=s.chroma_persist_dir)
col = client.get_or_create_collection(s.chroma_collection)

DROP = [
    "内蒙古阿拉善新井煤业露天煤矿“2·22”特别重大坍塌事故调查报告",
    "宁夏银川富洋烧烤店“6•21”特别重大燃气爆炸事故调查报告",
    "河南安阳市凯信达商贸有限公司“11·21”特别重大火灾事故调查报告",
]

for title in DROP:
    got = col.get(where={"title": title}, include=[])
    ids = got["ids"]
    print(f"删除 Chroma 块: {title[:40]}… {len(ids)} 块")
    if ids:
        col.delete(ids=ids)

# MySQL 同步删除（knowledge_document name 匹配）
with SessionLocal() as db:
    for title in DROP:
        r = db.execute(text("DELETE FROM knowledge_document WHERE name = :t"), {"t": title})
        print(f"MySQL 删除行: {title[:40]}… {r.rowcount} 行")
        db.commit()

client.close()
print("完成：3 个重复文档已从 Chroma + MySQL 删除")
