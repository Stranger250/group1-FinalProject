"""离线知识库构建管道（M1）：clean → parser → ref → loader。

数据真源：crawler_output/ 28 部法规 JSON；
清洗契约：docs/数据格式与建库注意事项.md §5；
分块/引用/元数据契约：docs/RAG优化方案.md §0.2 / §0.3 / §1.1-1.3。
"""
