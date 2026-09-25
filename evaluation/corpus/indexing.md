# 上传与索引链路

资料上传后先以安全生成的 upload_id 保存，随后依次经历 queued、parsing、chunking、embedding、persisting 和 ready。每个任务公开 stage、stage_index、stage_total、chunk_count 和事件时间；解析失败进入 error。相同知识库中重新上传同名资料会使用稳定 source identity 做增量清理，避免重复片段。
