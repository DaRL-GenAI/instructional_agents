# 如何获取 Task ID

## 方法1：通过前端界面（最简单）

1. 打开 `frontend/index.html`
2. 填写表单并提交任务
3. 提交后，Task ID 会显示在页面上
4. 或者在浏览器控制台（F12）中查看，会打印 `Task ID: xxx`

## 方法2：通过 API 提交任务获取

```bash
# 提交一个任务
curl -X POST http://localhost:8000/api/course/generate \
  -H "Content-Type: application/json" \
  -H "X-OpenAI-API-Key: your-api-key" \
  -d '{
    "course_name": "测试课程",
    "model_name": "gpt-4o-mini",
    "exp_name": "test"
  }'

# 响应示例：
# {"task_id": "abc-123-def-456", "status": "started", "message": "Course generation started"}
```

## 方法3：查看所有任务（需要重启服务）

如果服务已更新，可以访问：
```bash
curl http://localhost:8000/api/tasks/list
```

## 方法4：使用测试页面

1. 打开 `frontend/test_logs.html`
2. 点击"📋 获取所有任务"按钮
3. 会显示所有可用的任务列表
4. 点击"使用"按钮自动填入 Task ID

## 方法5：从浏览器控制台获取

如果任务正在运行：

1. 打开浏览器开发者工具（F12）
2. 在 Console 标签运行：
```javascript
// 查看当前任务 ID（如果前端代码中有存储）
console.log(currentTaskId);

// 或者查看最近的任务
fetch('http://localhost:8000/api/tasks/list')
  .then(r => r.json())
  .then(data => {
    console.log('所有任务:', data);
    if (data.tasks.length > 0) {
      console.log('最新的任务 ID:', data.tasks[0].task_id);
    }
  });
```

## 临时测试：创建一个新任务

如果你想快速测试，可以创建一个简单的测试任务：

```bash
# 在浏览器控制台运行
fetch('http://localhost:8000/api/course/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-OpenAI-API-Key': 'your-key-here'
  },
  body: JSON.stringify({
    course_name: '测试课程',
    model_name: 'gpt-4o-mini',
    exp_name: 'test_logs'
  })
})
.then(r => r.json())
.then(data => {
  console.log('Task ID:', data.task_id);
  // 复制这个 task_id 到测试页面
});
```

## 注意事项

- Task ID 是 UUID 格式，例如：`550e8400-e29b-41d4-a716-446655440000`
- 任务在服务重启后会丢失（因为存储在内存中）
- 如果服务重启，需要重新提交任务获取新的 Task ID

