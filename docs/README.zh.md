<div align="right" style="margin-bottom: 20px; margin-top: 10px;">
  <button onclick="switchLanguage('en')" id="lang-en" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #e2e8f0; background: white; color: #64748b; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇺🇸 English</button>
  <button onclick="switchLanguage('zh')" id="lang-zh" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #14b8a6; background: #14b8a6; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇨🇳 中文</button>
</div>

<script>
function switchLanguage(lang) {
    localStorage.setItem('preferredLanguage', lang);
    if (lang === 'en') {
        window.location.href = window.location.pathname.replace('.zh.md', '.md');
    } else {
        window.location.href = window.location.pathname.replace('.md', '.zh.md');
    }
}
document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferredLanguage') || 'zh';
    if (savedLang === 'en' && window.location.pathname.includes('.zh.md')) {
        window.location.href = window.location.pathname.replace('.zh.md', '.md');
    }
});
</script>

<style>
button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>

# 开发文档

本目录包含开发和调试相关的文档。

## 文档列表

- **IMPLEMENTATION_SUMMARY.md** - 实现总结和技术细节
- **DEBUG_LOGS.md** - 日志流调试指南
- **HOW_TO_GET_TASK_ID.md** - 如何获取 Task ID（调试用）

## 注意

这些文档主要用于开发和调试，普通用户不需要查看。

