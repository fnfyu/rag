# 离线评测

标注问题集由 query、collection_name 和带 grade 的 relevance 组成。Recall@K 衡量前 K 个结果覆盖了多少相关片段，MRR 只看第一个相关结果的位置，nDCG@K 使用 2^grade-1 的 graded gain 计算排序质量。评测运行必须记录数据集 fingerprint、切点、embedding、BM25 分词器、reranker 和 chunking 配置；脚本只检索，不调用生成模型。
