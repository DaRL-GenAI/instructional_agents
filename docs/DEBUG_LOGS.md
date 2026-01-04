# 日志流调试指南

## 问题诊断步骤

### 1. 检查日志流连接

打开浏览器开发者工具（F12），在 Console 标签中查看：

```javascript
// 应该看到这些日志：
Starting log stream for task: <task_id>
Log stream connected, status: 200
```

### 2. 检查网络请求

在 Network 标签中：
- 查找 `/api/course/logs/{task_id}/stream` 请求
- 检查状态码（应该是 200）
- 查看 Response 标签，应该看到 SSE 数据流

### 3. 检查日志队列

如果连接正常但没有日志，可能是：
- 日志队列没有正确初始化
- 日志捕获没有工作
- 任务已经完成

### 4. 手动测试日志流

在浏览器控制台运行：

```javascript
// 1. 先提交一个任务
fetch('http://localhost:8000/api/course/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-OpenAI-API-Key': 'your-key'
  },
  body: JSON.stringify({
    course_name: 'Test Course',
    model_name: 'gpt-4o-mini',
    exp_name: 'test'
  })
}).then(r => r.json()).then(data => {
  console.log('Task ID:', data.task_id);
  
  // 2. 连接日志流
  fetch(`http://localhost:8000/api/course/logs/${data.task_id}/stream`, {
    headers: {
      'X-OpenAI-API-Key': 'your-key'
    }
  }).then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    function read() {
      reader.read().then(({done, value}) => {
        if (done) return;
        buffer += decoder.decode(value);
        const lines = buffer.split('\n');
        buffer = lines.pop();
        lines.forEach(line => {
          if (line.startsWith('data: ')) {
            console.log('Received:', line);
          }
        });
        read();
      });
    }
    read();
  });
});
```

## 常见问题

### 问题1：连接成功但没有日志

**原因**：日志队列可能为空，或者日志捕获没有工作

**解决**：
- 检查任务是否正在运行
- 查看 docker logs 确认有输出
- 确认 LogCapture 正确替换了 sys.stdout

### 问题2：连接失败

**原因**：
- API 服务未运行
- CORS 问题
- 任务 ID 不存在

**解决**：
- 检查 API 服务状态：`docker compose ps`
- 检查健康状态：`curl http://localhost:8000/health`
- 查看浏览器控制台错误

### 问题3：日志延迟显示

**原因**：日志队列处理频率问题

**解决**：已优化为每 0.05 秒处理一次，应该足够快

## 调试技巧

1. **添加更多日志**：在关键位置添加 console.log
2. **检查队列大小**：在 API 中添加端点查看队列状态
3. **测试简单消息**：先测试是否能接收连接消息

