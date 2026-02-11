<script setup lang="js">
import { onMounted, ref } from 'vue'
import { Chat } from '@ai-sdk/vue'
import { DocumentAdd, Promotion, Plus, Loading } from '@element-plus/icons-vue'

const current_conversation_id=ref(null) 

const myOnData=(part)=>{ 
  if (part.type=='data-sources'){
     const sources=part.data 
     const last=chat.messages[chat.messages.length-1] 
     if(last && last.role=='assistant') last.sources=sources 
    } 
  } 

const createChat=()=>{
   return new Chat({
     api: `http://localhost:8000/api/chat/${current_conversation_id.value}`, 
     stream: true, 
     headers: { 'Accept': 'text/event-stream', 'Content-Type': 'application/json' },
      onData: myOnData }) 
    } 

let chat=ref(createChat())


onMounted(async()=>{ 
  await loadConversations()
   if (conversations.value.length>0){
     await loadConversation(conversations.value[0].id) } 
     else{ 
      await createNewConversation() 
    } 
    })


onMounted(async()=>{
  await loadConversations()

  if (conversations.value.length>0){
    await loadConversation(conversations.value[0].id)
  }
  else{
    await createNewConversation()
  }
})

const conversations=ref([])

const input = ref("")
const isUploading = ref(false)
const fileInputRef = ref(null)

const handleSubmit = (e) => {
  e.preventDefault();
  chat.sendMessage({ text:input.value+"---"+current_conversation_id.value });
  input.value = "";
};

// 点击“上传文件”按钮时，触发隐藏的文件选择框
const handleClickUpload = () => {
  if (fileInputRef.value) {
    fileInputRef.value.click()
  }
}

// 选择文件后，调用上传接口
const handleFileChange = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  // if (!current_conversation_id.value) {
  //   await createNewConversation()z
  // }

  const formData = new FormData()
  formData.append('file', file)
  formData.append("conversation_id",current_conversation_id.value)
console.log(current_conversation_id.value)
  try {
    isUploading.value = true
    const res = await fetch('http://127.0.0.1:8000/upload', {
      method: 'POST',
      body: formData,
    })

    if (!res.ok) {
      const errText = await res.text()
      console.error('上传失败', errText)
      chat.messages.push({
        id: `upload-error-${Date.now()}`,
        role: 'assistant',
        parts: [{ type: 'text', text: `文件上传失败：${errText}` }]
      })
      return
    }

    const data = await res.json()
    console.log('上传成功', data)

    // 用后端返回的 message 在对话里提示用户
    chat.messages.push({
      id: `upload-${Date.now()}`,
      role: 'assistant',
      parts: [
        { type: 'text', text: `文件「${data.filename}」上传成功。` },
        { type: 'text', text: data.message || '文件正在后台解析，请稍等再就此提问。' }
      ]
    })

    const upload_id=data.upload_id

    const current_id=setInterval(
      async () => {
      try {
        const resp = await fetch(`http://127.0.0.1:8000/upload/status?upload_id=${upload_id}`)
        if (!resp.ok) return
        const status = await resp.json()
        if (status.status === 'done') {
          clearInterval(current_id)
          chat.messages.push({
            id: `upload-done-${Date.now()}`,
            role: 'assistant',
            parts: [
              { type: 'text', text: `文件「${data.filename}」解析完成，现在可以针对这份文件提问了。` }
            ]
          })
        }
         } catch (err) {
        console.error('查询上传状态出错', err)
      }
    }, 3000) // 每 3 秒查一次
  } catch (err) {
    console.error('上传出错', err)
    chat.messages.push({
      id: `upload-error-${Date.now()}`,
      role: 'assistant',
      parts: [{ type: 'text', text: `文件上传出错：${String(err)}` }]
    })
  } finally {
    isUploading.value = false
    event.target.value = ''
  }
}

const clearMessages=()=>{
  chat.messages.length=0
}

const handleClickSource=(s)=>{
  console.log('点击溯源：', s)
  if (s.start_line && s.source_path) {
    const vscodeUrl=`vscode://file/${s.source_path}:${s.start_line}`
    window.location.href = vscodeUrl;
  }
  else {
      console.log("非代码文件，当前路径：", s.source_path);
      alert(`正在查看：${s.filename}\n位置：第 ${s.page_number || '未知'} 页`);
  }
}

const loadConversations=async()=>{
  try{
    const res=await fetch('http://127.0.0.1:8000/conversations/list')
    if( res.ok){
      conversations.value=await res.json()
    }
  
  }
  catch(err){
    console.log("加载对话列表失败",err)
  }
}

const createNewConversation=async()=>{
  try{
    const res=await fetch("http://127.0.0.1:8000/conversations/create",{
      method:"post",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '新对话' })
    })
    if(res.ok){
      const newConv=await res.json()
      await loadConversations() 
      current_conversation_id.value=newConv.id
      chat=createChat()
      clearMessages()
      console.log('新对话已创建:', newConv.id)
    }

    

  }
  catch(err){
    console.error('创建对话失败',err)
  }
}

const loadConversation=async(conversation_id)=>{
  current_conversation_id.value=conversation_id
  chat=createChat()
  try{
    const res=await fetch(`http://127.0.0.1:8000/conversations/list/${conversation_id}`)
    if(res.ok){
      const messages=await res.json()
      chat.messages=messages
    }

    

  }
  catch(err){
    console.error('加载对话失败',err)
  }

}

const formatTime = (isoString) => {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diff = now - date
  
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`
  
  return date.toLocaleDateString()
}

</script>

<template>
  <div class="chat-wrapper">
    <el-container class="main-layout">
      <el-aside width="240px" class="sidebar hidden-sm-and-down">
        <div class="sidebar-header">
          <el-button type="primary" plain class="new-chat-btn" icon="Plus" @click="createNewConversation">新建对话</el-button>
        </div>
        <div class="history-list">
        <div 
          v-for="conv in conversations" 
          :key="conv.id"
          :class="['history-item', { active: current_conversation_id === conv.id }]"
          @click="loadConversation(conv.id)"
        >
        <div class="history-title">{{ conv.title }}</div>
        <div class="history-meta">
          {{ formatTime(conv.updated_at) }}
          </div>
      </div>
    
      <div v-if="conversations.length === 0" class="empty-hint">
        暂无对话记录
       </div>
      </div>
      </el-aside>

      <el-container class="content-container">
        <el-header class="chat-header">
          <div class="header-content">
            <span class="status-dot"></span>
            <span class="title">RAG 智能助手</span>
          </div>
        </el-header>

        <el-main class="chat-main" id="chatMain">
          <div v-for="(m, index) in chat.messages" 
               :key="m.id ? m.id : index"
               :class="['message-row', m.role]">
            
            <el-avatar v-if="m.role === 'assistant'" :size="36" class="avatar" src="https://api.dicebear.com/7.x/bottts/svg?seed=Felix" />
            
            <div class="bubble-container">
              <div class="bubble">
                <div v-for="(part, index) in m.parts" :key="index">
                  <p v-if="part.type === 'text'" class="text-content">{{ part.text }}</p>
                </div>

                 <!-- 溯源区域 -->
                <div v-if="m.sources && m.sources.length && !chat.isLoading", class="source-list">
                <div class="source-title">参考资料：</div>
                  <div    
                    v-for="s in m.sources" 
                    :key="s.id" 
                    class="source-item"
                    @click="handleClickSource(s)"
                   >
                  {{ s.filename || '未知文件' }} 
                  <!-- 情况 A：纯文本/代码（带行号） -->
                  <span v-if="s.start_line" class="source-detail">
                    （第 {{ s.start_line }} - {{ s.end_line }} 行）
                  </span>
    
                  <!-- 情况 B：PDF/Docx（带页码） -->
                  <span v-else-if="s.page_number" class="source-detail">
                  （第 {{ s.page_number || s.page }} 页）
                  </span>

                  <!-- 情况 C：兜底显示 Chunk 序号 -->
                  <span v-else-if="s.chunk_index" class="source-detail">
                    （片段 #{{ s.chunk_index }}）
                  </span>
                </div>
               </div>
              </div>  
              <span class="time-stamp">{{ new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) }}</span>
            </div>

            <el-avatar v-if="m.role === 'user'" :size="36" class="avatar" src="https://api.dicebear.com/7.x/adventurer/svg?seed=Aneka" />
          </div>
          
          <div v-if="isUploading" class="message-row assistant">
            <el-avatar :size="36" class="avatar" src="https://api.dicebear.com/7.x/bottts/svg?seed=Felix" />
            <div class="bubble loading-bubble">
              <el-icon class="is-loading"><Loading /></el-icon> 正在努力解析文件...
            </div>
          </div>
        </el-main>

        <el-footer class="chat-footer" height="auto">
          <div class="input-box-wrapper">
            <form @submit="handleSubmit" class="input-form">
              <el-input
                v-model="input"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="问点什么吧..."
                resize="none"
                @keydown.enter.prevent="handleSubmit"
                :disabled="chat.isLoading || isUploading"
                class="custom-input"
              >
              </el-input>
              
              <div class="action-bar">
                <div class="left-actions">
                  <el-tooltip  content="上传文档解析" placement="top">
                    <el-button circle @click="handleClickUpload" :loading="isUploading" >
                      <el-icon><DocumentAdd /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
                <el-button 
                  type="primary" 
                  class="send-btn" 
                  @click="handleSubmit" 
                  :loading="chat.isLoading"
                  :disabled="!input.trim()"
                >
                  <el-icon><Promotion /></el-icon>
                </el-button>
              </div>
            </form>
          </div>
          
          <input ref="fileInputRef" type="file" style="display: none" @change="handleFileChange" />
          <p class="footer-tips">内容由 AI 生成，请核查重要信息</p>
        </el-footer>
      </el-container>
    </el-container>
  </div>
</template>

<style scoped>
/* 全局容器 */
.chat-wrapper {
  height: 100vh;
  background-color: #f9fafb;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.main-layout {
  height: 100%;
}

/* 侧边栏样式 */
.sidebar {
  background-color: #ffffff;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  padding: 16px;
}
.new-chat-btn {
  width: 100%;
  margin-bottom: 20px;
  border-radius: 8px;
}
.history-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #4b5563;
  transition: all 0.2s;
}
.history-item:hover { background: #f3f4f6; }
.history-item.active { background: #eff6ff; color: #2563eb; font-weight: 500; }

/* 聊天主体 */
.chat-header {
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  padding: 0 24px;
}
.header-content {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
}
.title { font-weight: 600; color: #111827; }

.chat-main {
  padding: 24px;
  scroll-behavior: smooth;
}

/* 气泡设计 */
.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  align-items: flex-start;
}
.user { justify-content: flex-end; }

.bubble-container {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}
.user .bubble-container { align-items: flex-end; }

.bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.6;
  position: relative;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.assistant .bubble {
  background-color: #ffffff;
  color: #374151;
  border: 1px solid #e5e7eb;
  border-top-left-radius: 2px;
}

.user .bubble {
  background-color: #2563eb;
  color: #ffffff;
  border-top-right-radius: 2px;
}

.text-content { margin: 0; white-space: pre-wrap; }

.time-stamp {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 4px;
}

/* 输入框区域 */
.chat-footer {
  padding: 20px 24px;
  background: transparent;
}
.input-box-wrapper {
  max-width: 800px;
  margin: 0 auto;
  background: #ffffff;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border: 1px solid #e5e7eb;
  padding: 8px;
}

.custom-input :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  font-size: 16px;
  padding: 8px 12px;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid #f3f4f6;
  margin-top: 4px;
}

.send-btn {
  border-radius: 8px;
  padding: 8px 20px;
}

.footer-tips {
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
  margin-top: 12px;
}

/* 动画 */
.loading-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
}

.source-list {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f3f4f6;
  font-size: 12px;
  color: #6b7280;
}

.source-title {
  margin-bottom: 4px;
}

.source-item {
  cursor: pointer;
  color: #2563eb;
  padding: 2px 0;
}

.source-item:hover {
  text-decoration: underline;
}
</style>