<div align="right" style="margin-bottom: 20px; margin-top: 10px;">
  <button onclick="switchLanguage('en')" id="lang-en" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #14b8a6; background: #14b8a6; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇺🇸 English</button>
  <button onclick="switchLanguage('zh')" id="lang-zh" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #e2e8f0; background: white; color: #64748b; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇨🇳 中文</button>
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
    const savedLang = localStorage.getItem('preferredLanguage') || 'en';
    if (savedLang === 'zh' && !window.location.pathname.includes('.zh.md')) {
        window.location.href = window.location.pathname.replace('.md', '.zh.md');
    }
});
</script>

<style>
button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>

# Development Documentation

This directory contains development and debugging related documentation.

## Document List

- **IMPLEMENTATION_SUMMARY.md** - Implementation summary and technical details
- **DEBUG_LOGS.md** - Log streaming debugging guide
- **HOW_TO_GET_TASK_ID.md** - How to get Task ID (for debugging)

## Note

These documents are primarily for development and debugging purposes. Regular users do not need to view them.

