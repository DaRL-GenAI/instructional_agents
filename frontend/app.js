// API Base URL - adjust if needed
const API_BASE_URL = 'http://localhost:8000';

// Localization
const translations = {
    zh: {
        pageTitle: 'Instructional Agents - 课程生成系统',
        heroTitle: '🎓 Instructional Agents',
        heroSubtitle: 'AI驱动的课程材料自动生成系统<br>让教学准备变得简单高效',
        apiSectionTitle: 'API 配置',
        apiKeyLabel: 'OpenAI API Key *',
        apiKeyPlaceholder: 'sk-...',
        apiKeyToggleShow: '👁️ 显示',
        apiKeyToggleHide: '🙈 隐藏',
        apiKeyNote: '您的 API Key 仅保存在浏览器本地，不会上传到服务器',
        saveApiKeyButton: '<span>💾</span><span>保存 API Key</span>',
        saveApiKeyButtonSaved: '✅ API Key 已保存',
        configSectionTitle: '课程配置',
        courseNameLabel: '课程名称 *',
        courseNamePlaceholder: '例如：机器学习导论',
        modelNameLabel: '模型选择',
        modelOptionMini: 'GPT-4o Mini (推荐)',
        modelOptionGpt4o: 'GPT-4o',
        modelOptionGpt4Turbo: 'GPT-4 Turbo',
        expNameLabel: '实验名称',
        expNamePlaceholder: '默认：default',
        copilotLabel: '启用 Copilot 模式（交互式反馈）',
        catalogModeLabel: 'Catalog 模式',
        catalogOptionNone: '不使用',
        catalogOptionDefault: '使用默认 Catalog',
        catalogOptionUpload: '上传 Catalog 文件',
        catalogOptionSelect: '选择已有 Catalog',
        catalogUploadLabel: '上传 Catalog JSON 文件',
        catalogUploadTip: '或直接在下方输入 JSON 数据',
        catalogSelectLabel: '选择 Catalog',
        catalogSelectLoading: '加载中...',
        catalogSelectPlaceholder: '选择 Catalog...',
        catalogJsonLabel: 'Catalog JSON 数据',
        catalogJsonPlaceholder: '{"student_profile": {...}, "instructor_preferences": {...}}',
        submitButtonText: '<span>🚀</span><span>开始生成课程</span>',
        submitButtonLoading: '⏳ 提交中...',
        progressSectionTitle: '生成进度',
        progressInitial: '初始化中...',
        logsTitle: '实时日志',
        clearLogsButton: '🗑️ 清空日志',
        logsPlaceholder: '等待日志输出...',
        resultsSectionTitle: '生成结果',
        resultsLoading: '加载文件列表...',
        footerText: 'Powered by <strong>Instructional Agents</strong> • AI 赋能的课程生成',
        alertApiKeyRequired: '请输入 API Key',
        confirmApiKeyFormat: 'API Key 通常以 "sk-" 开头。确定要继续吗？',
        alertApiKeySaved: '✅ API Key 已保存',
        alertProvideApiKey: '请先输入并保存 OpenAI API Key',
        submitFailed: '提交失败: {message}',
        invalidCatalogJson: 'Catalog JSON 格式无效',
        errorProgressSectionMissing: '错误：找不到进度区域元素',
        logConnecting: '🔗 正在连接日志流...',
        logConnected: '📡 已连接到日志流...',
        logStreamEnded: '📡 日志流已结束',
        logTaskCompleted: '✅ 任务完成！',
        logErrorMessage: '❌ 错误: {message}',
        logInactivityWarning: '⚠️ 10秒内未收到日志，可能任务尚未开始或日志捕获未工作',
        logReadError: '⚠️ 日志流读取错误: {message}',
        logReconnecting: '🔄 3秒后尝试重新连接...',
        logConnectFailed: '❌ 无法连接到日志流: {message}',
        logCheckService: '💡 提示: 请检查 API 服务是否正常运行',
        logEmptyResponse: '❌ 响应体为空，无法读取日志流',
        logParseError: '[解析错误] {content}',
        logNewFiles: '📄 新文件已生成: {fileNames}',
        resultsGenerating: '📦 正在生成中... 以下文件已可用：',
        resultsCompleted: '✅ 全部完成！共生成 {count} 个文件',
        resultsNone: '暂无生成的文件',
        fileLocationTitle: '📁 文件位置',
        fileLocationPathLabel: '本地路径：',
        fileLocationCopy: '📋 复制路径',
        fileLocationOpen: '📂 打开文件夹',
        fileLocationFinder: '🔍 在 Finder 中显示',
        fileLocationTip: '💡 提示：如果“打开文件夹”按钮无法工作，请手动在 Finder 中打开上述路径',
        rootDirectory: '根目录',
        unknownFileType: '未知类型',
        copyPathSuccess: '✅ 路径已复制到剪贴板！\n\n{path}',
        copyPathFailure: '❌ 无法自动复制，请手动复制：\n\n{path}',
        downloadLabel: '📥 下载',
        newBadgeLabel: '<span class="new-badge">🆕 新</span>',
        statusPending: '等待中',
        statusRunning: '运行中',
        statusCompleted: '已完成',
        statusFailed: '失败',
        progressTextTemplate: '进度: {progress}% - {status}',
        currentStageLabel: '当前阶段: {stage}',
        errorLabel: '错误: {message}',
        errorLoadResults: '加载结果失败: {message}',
        catalogListFailed: '无法加载 Catalog 列表',
        catalogSelectDefault: '选择 Catalog...',
        uploadCatalogFailed: '上传 Catalog 文件失败',
        modeGenerate: '生成新课程',
        modeOptimize: '优化已有材料',
        pptxLabel: '同时生成 PPTX 幻灯片',
        optimizeModeLabel: '优化方式',
        optimizeModeRegenerate: '逐张重新生成（整章重写）',
        optimizeModeRefine: '局部精修（仅改相关帧）',
        optimizeModeTip: '重新生成：每张幻灯片整体重写。局部精修：只定位并改写与需求相关的帧，其余保持不变。',
        optimizeSectionTitle: '优化配置',
        optimizeSubmitButton: '<span>🔧</span><span>开始优化</span>',
        optimizeProgressTitle: '优化进度',
        optimizeResultsTitle: '优化结果',
        chapterNamePlaceholder2: '留空则优化全部章节',
        taskFailedFallback: '任务失败',
        slideOptimizationTitle: '📚 幻灯片优化',
        slideOptimizationDescription: '上传您的PDF幻灯片，系统将分析内容并提供改进建议',
        slidePdfFilesLabel: '上传PDF幻灯片文件 *',
        slidePdfFilesTip: '可以选择多个PDF文件（支持Ctrl/Cmd+点击多选）',
        optimizationModeLabel: '优化模式',
        optimizationModeChapter: '优化指定章节',
        optimizationModeAll: '优化全部课程',
        chapterNameLabel: '章节名称',
        chapterNamePlaceholder: '例如：Chapter 3 或 第3章',
        chapterNameTip: '支持格式：Chapter 1, Chapter1, Ch1, 第1章 等',
        userRequirementsLabel: '优化需求描述 *',
        userRequirementsPlaceholder: '例如：添加更多实例、改进解释、增加代码示例等',
        optimizeSlidesButton: '<span>🔍</span><span>开始分析优化</span>',
        optimizationResultsTitle: '分析结果',
        optimizationResultsLoading: '分析中...',
        slideUploadSuccess: '✅ 成功上传 {count} 个PDF文件',
        slideUploadFailed: '❌ 上传失败: {message}',
        slideNoFilesSelected: '请至少选择一个PDF文件',
        slideOptimizationStarted: '🔍 开始分析优化...',
        slideOptimizationSuccess: '✅ 分析完成！',
        slideOptimizationFailed: '❌ 分析失败: {message}',
        slideStorageIdLabel: '存储ID',
        slideAnalysisLabel: '内容分析',
        slideRecommendationsLabel: '改进建议',
        slideRelevantContentLabel: '相关内容',
        generateLatexTitle: '生成改进后的幻灯片',
        generateLatexDescription: '基于分析结果和改进建议，生成改进后的LaTeX幻灯片文件',
        generateLatexButton: '<span>📝</span><span>生成LaTeX文件</span>',
        generateLatexLoading: '⏳ 正在生成LaTeX文件...',
        generateLatexSuccess: '✅ LaTeX文件生成成功！',
        generateLatexFailed: '❌ 生成失败: {message}',
        downloadLatexLabel: '📥 下载LaTeX文件',
        downloadEnhancedContentLabel: '📄 下载增强内容',
        feedbackTitle: '提供反馈（可选）',
        feedbackSlidesLabel: '对幻灯片的反馈:',
        feedbackOverallLabel: '总体反馈:',
        toggleFeedbackButton: '添加反馈',
        improveTitle: '迭代改进',
        improveDescription: '基于生成的幻灯片提供反馈，系统将重新生成改进版本',
        improveButton: '基于反馈重新生成',
        improveLoading: '⏳ 正在重新生成...'
    },
    en: {
        pageTitle: 'Instructional Agents - Course Generation System',
        heroTitle: '🎓 Instructional Agents',
        heroSubtitle: 'AI-powered course material generation<br>Makes lesson prep fast and easy',
        apiSectionTitle: 'API Configuration',
        apiKeyLabel: 'OpenAI API Key *',
        apiKeyPlaceholder: 'sk-...',
        apiKeyToggleShow: '👁️ Show',
        apiKeyToggleHide: '🙈 Hide',
        apiKeyNote: 'Your API Key is stored locally in the browser and never uploaded to the server',
        saveApiKeyButton: '<span>💾</span><span>Save API Key</span>',
        saveApiKeyButtonSaved: '✅ API Key Saved',
        configSectionTitle: 'Course Settings',
        courseNameLabel: 'Course Name *',
        courseNamePlaceholder: 'e.g., Introduction to Machine Learning',
        modelNameLabel: 'Model Selection',
        modelOptionMini: 'GPT-4o Mini (Recommended)',
        modelOptionGpt4o: 'GPT-4o',
        modelOptionGpt4Turbo: 'GPT-4 Turbo',
        expNameLabel: 'Experiment Name',
        expNamePlaceholder: 'Default: default',
        copilotLabel: 'Enable Copilot Mode (Interactive Feedback)',
        catalogModeLabel: 'Catalog Mode',
        catalogOptionNone: 'Do not use',
        catalogOptionDefault: 'Use default catalog',
        catalogOptionUpload: 'Upload catalog file',
        catalogOptionSelect: 'Select existing catalog',
        catalogUploadLabel: 'Upload Catalog JSON file',
        catalogUploadTip: 'Or paste JSON data below',
        catalogSelectLabel: 'Select Catalog',
        catalogSelectLoading: 'Loading...',
        catalogSelectPlaceholder: 'Select a catalog...',
        catalogJsonLabel: 'Catalog JSON Data',
        catalogJsonPlaceholder: '{"student_profile": {...}, "instructor_preferences": {...}}',
        submitButtonText: '<span>🚀</span><span>Generate Course</span>',
        submitButtonLoading: '⏳ Submitting...',
        progressSectionTitle: 'Progress',
        progressInitial: 'Initializing...',
        logsTitle: 'Real-time Logs',
        clearLogsButton: '🗑️ Clear Logs',
        logsPlaceholder: 'Waiting for log output...',
        resultsSectionTitle: 'Generated Results',
        resultsLoading: 'Loading file list...',
        footerText: 'Powered by <strong>Instructional Agents</strong> • AI-Powered Course Generation',
        alertApiKeyRequired: 'Please enter an API Key',
        confirmApiKeyFormat: 'API Keys usually start with "sk-". Continue anyway?',
        alertApiKeySaved: '✅ API Key Saved',
        alertProvideApiKey: 'Please enter and save your OpenAI API Key first',
        submitFailed: 'Submission failed: {message}',
        invalidCatalogJson: 'Invalid JSON format in catalog data',
        errorProgressSectionMissing: 'Error: Progress section element not found',
        logConnecting: '🔗 Connecting to log stream...',
        logConnected: '📡 Connected to log stream...',
        logStreamEnded: '📡 Log stream ended',
        logTaskCompleted: '✅ Task completed!',
        logErrorMessage: '❌ Error: {message}',
        logInactivityWarning: '⚠️ No log messages for 10 seconds; the task may not have started yet or logs are unavailable',
        logReadError: '⚠️ Log stream read error: {message}',
        logReconnecting: '🔄 Retrying in 3 seconds...',
        logConnectFailed: '❌ Unable to connect to log stream: {message}',
        logCheckService: '💡 Tip: Check if the API service is running',
        logEmptyResponse: '❌ Response body was empty; can\'t read log stream',
        logParseError: '[Parse error] {content}',
        logNewFiles: '📄 New files ready: {fileNames}',
        resultsGenerating: '📦 Generating... The following files are ready:',
        resultsCompleted: '✅ All done! {count} files generated',
        resultsNone: 'No files generated yet',
        fileLocationTitle: '📁 File Location',
        fileLocationPathLabel: 'Local path:',
        fileLocationCopy: '📋 Copy path',
        fileLocationOpen: '📂 Open folder',
        fileLocationFinder: '🔍 Show in Finder',
        fileLocationTip: '💡 Tip: If “Open folder” does not work, open the path manually in Finder',
        rootDirectory: 'Root directory',
        unknownFileType: 'Unknown type',
        copyPathSuccess: '✅ Path copied to clipboard!\n\n{path}',
        copyPathFailure: '❌ Could not copy automatically. Please copy manually:\n\n{path}',
        downloadLabel: '📥 Download',
        newBadgeLabel: '<span class="new-badge">🆕 New</span>',
        statusPending: 'Pending',
        statusRunning: 'Running',
        statusCompleted: 'Completed',
        statusFailed: 'Failed',
        progressTextTemplate: 'Progress: {progress}% - {status}',
        currentStageLabel: 'Current stage: {stage}',
        errorLabel: 'Error: {message}',
        errorLoadResults: 'Failed to load results: {message}',
        catalogListFailed: 'Failed to load catalog list',
        catalogSelectDefault: 'Select Catalog...',
        uploadCatalogFailed: 'Failed to upload catalog file',
        modeGenerate: 'Generate Course',
        modeOptimize: 'Optimize Materials',
        pptxLabel: 'Also generate PPTX slides',
        optimizeModeLabel: 'Optimization Method',
        optimizeModeRegenerate: 'Regenerate (rewrite every slide)',
        optimizeModeRefine: 'Localized Refine (edit only relevant frames)',
        optimizeModeTip: 'Regenerate: rewrite each slide wholesale. Localized Refine: locate and rewrite only the frames relevant to your requirements, leaving the rest untouched.',
        optimizeSectionTitle: 'Optimization Settings',
        optimizeSubmitButton: '<span>🔧</span><span>Start Optimization</span>',
        optimizeProgressTitle: 'Optimization Progress',
        optimizeResultsTitle: 'Optimization Results',
        chapterNamePlaceholder2: 'Leave empty to optimize all chapters',
        taskFailedFallback: 'Task failed',
        slideOptimizationTitle: '📚 Slide Optimization',
        slideOptimizationDescription: 'Upload your PDF slides, and the system will analyze the content and provide improvement suggestions',
        slidePdfFilesLabel: 'Upload PDF Slide Files *',
        slidePdfFilesTip: 'You can select multiple PDF files (Ctrl/Cmd+click to select multiple)',
        optimizationModeLabel: 'Optimization Mode',
        optimizationModeChapter: 'Optimize Specific Chapter',
        optimizationModeAll: 'Optimize All Chapters',
        chapterNameLabel: 'Chapter Name',
        chapterNamePlaceholder: 'e.g., Chapter 3 or Chapter 3',
        chapterNameTip: 'Supported formats: Chapter 1, Chapter1, Ch1, etc.',
        userRequirementsLabel: 'Optimization Requirements *',
        userRequirementsPlaceholder: 'e.g., Add more examples, improve explanations, add code samples, etc.',
        optimizeSlidesButton: '<span>🔍</span><span>Start Analysis</span>',
        optimizationResultsTitle: 'Analysis Results',
        optimizationResultsLoading: 'Analyzing...',
        slideUploadSuccess: '✅ Successfully uploaded {count} PDF files',
        slideUploadFailed: '❌ Upload failed: {message}',
        slideNoFilesSelected: 'Please select at least one PDF file',
        slideOptimizationStarted: '🔍 Starting analysis...',
        slideOptimizationSuccess: '✅ Analysis completed!',
        slideOptimizationFailed: '❌ Analysis failed: {message}',
        slideStorageIdLabel: 'Storage ID',
        slideAnalysisLabel: 'Content Analysis',
        slideRecommendationsLabel: 'Improvement Recommendations',
        slideRelevantContentLabel: 'Relevant Content',
        generateLatexTitle: 'Generate Enhanced Slides',
        generateLatexDescription: 'Generate improved LaTeX slide files based on analysis results and recommendations',
        generateLatexButton: '<span>📝</span><span>Generate LaTeX</span>',
        generateLatexLoading: '⏳ Generating LaTeX files...',
        generateLatexSuccess: '✅ LaTeX files generated successfully!',
        generateLatexFailed: '❌ Generation failed: {message}',
        downloadLatexLabel: '📥 Download LaTeX File',
        downloadEnhancedContentLabel: '📄 Download Enhanced Content',
        feedbackTitle: 'Provide Feedback (Optional)',
        feedbackSlidesLabel: 'Feedback on Slides:',
        feedbackOverallLabel: 'Overall Feedback:',
        toggleFeedbackButton: 'Add Feedback',
        improveTitle: 'Iterative Improvement',
        improveDescription: 'Provide feedback on the generated slides, and the system will regenerate an improved version',
        improveButton: 'Regenerate Based on Feedback',
        improveLoading: '⏳ Regenerating...'
    }
};

let currentLanguage = localStorage.getItem('ui_language') || 'zh';

// State management
let currentTaskId = null;
let statusCheckInterval = null;
let fileCheckInterval = null;
let logEventSource = null;
let apiKey = null;
let knownFiles = new Set(); // Track files we've already displayed
let submitButtonIsLoading = false;
let lastProgressStatus = null;

function getLanguageData(lang = currentLanguage) {
    return translations[lang] || translations.zh;
}

function t(key, params = {}) {
    const langData = getLanguageData();
    let template = langData[key];
    if (template === undefined) {
        const fallback = translations.en[key] || translations.zh[key];
        template = fallback !== undefined ? fallback : key;
    }
    return Object.keys(params).reduce((result, paramKey) => {
        const value = params[paramKey];
        const regex = new RegExp(`\\{${paramKey}\\}`, 'g');
        return result.replace(regex, value);
    }, template);
}

function applyTranslations() {
    const langData = getLanguageData();
    document.documentElement.lang = currentLanguage === 'zh' ? 'zh-CN' : 'en';

    const pageTitleElement = document.querySelector('title[data-i18n="pageTitle"]');
    if (pageTitleElement) {
        pageTitleElement.textContent = langData.pageTitle;
    }
    document.title = langData.pageTitle;

    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        const target = element.getAttribute('data-i18n-target') || 'text';
        const translation = t(key);
        if (translation === undefined) {
            return;
        }
        if (target === 'html') {
            element.innerHTML = translation;
        } else {
            element.textContent = translation;
        }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        const translation = t(key);
        if (translation !== undefined) {
            element.setAttribute('placeholder', translation);
        }
    });

    updateLanguageToggleButton();
    updateApiKeyToggleLabel();
    updateSubmitButtonLabel();
    if (lastProgressStatus) {
        updateProgress(lastProgressStatus);
    }
}

function updateLanguageToggleButton() {
    const toggleButton = document.getElementById('language-toggle');
    if (!toggleButton) {
        return;
    }
    if (currentLanguage === 'zh') {
        toggleButton.textContent = '🇺🇸 English';
    } else {
        toggleButton.textContent = '🇨🇳 中文';
    }
}

function updateApiKeyToggleLabel() {
    const toggleBtn = document.getElementById('toggle-api-key');
    const input = document.getElementById('api-key');
    if (!toggleBtn || !input) {
        return;
    }
    if (input.type === 'password') {
        toggleBtn.textContent = t('apiKeyToggleShow');
    } else {
        toggleBtn.textContent = t('apiKeyToggleHide');
    }
}

function setLanguage(lang) {
    if (!translations[lang]) {
        return;
    }
    currentLanguage = lang;
    localStorage.setItem('ui_language', currentLanguage);
    applyTranslations();
    updateApiKeyStatus(!!apiKey);
    const progressText = document.getElementById('progress-text');
    if (progressText && !progressText.dataset.manual) {
        progressText.textContent = t('progressInitial');
    }
}

function toggleLanguage() {
    const nextLanguage = currentLanguage === 'zh' ? 'en' : 'zh';
    setLanguage(nextLanguage);
}

function updateSubmitButtonLabel() {
    const submitBtn = document.getElementById('submit-btn');
    if (!submitBtn) {
        return;
    }
    if (submitButtonIsLoading) {
        submitBtn.textContent = t('submitButtonLoading');
    } else {
        submitBtn.innerHTML = t('submitButtonText');
    }
    submitBtn.disabled = submitButtonIsLoading;
}

function setSubmitButtonLoading(isLoading) {
    submitButtonIsLoading = isLoading;
    const submitBtn = document.getElementById('submit-btn');
    if (!submitBtn) {
        return;
    }
    updateSubmitButtonLabel();
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    applyTranslations();
    loadApiKey();
    setupEventListeners();
    loadCatalogs();
});

// Load API Key from localStorage
function loadApiKey() {
    const saved = localStorage.getItem('openai_api_key');
    if (saved) {
        apiKey = saved;
        document.getElementById('api-key').value = saved;
        updateApiKeyStatus(true);
    } else {
        updateApiKeyStatus(false);
    }
}

// Save API Key to localStorage
function saveApiKey() {
    const key = document.getElementById('api-key').value.trim();
    if (!key) {
        alert(t('alertApiKeyRequired'));
        return;
    }
    if (!key.startsWith('sk-')) {
        if (!confirm(t('confirmApiKeyFormat'))) {
            return;
        }
    }
    apiKey = key;
    localStorage.setItem('openai_api_key', key);
    updateApiKeyStatus(true);
    alert(t('alertApiKeySaved'));
}

// Update API Key status display
function updateApiKeyStatus(saved) {
    const saveBtn = document.getElementById('save-api-key');
    if (saved) {
        saveBtn.textContent = t('saveApiKeyButtonSaved');
        saveBtn.style.backgroundColor = '#10b981';
    } else {
        saveBtn.innerHTML = t('saveApiKeyButton');
        saveBtn.style.backgroundColor = '';
    }
}

// Toggle API Key visibility
function toggleApiKeyVisibility() {
    const input = document.getElementById('api-key');
    const toggleBtn = document.getElementById('toggle-api-key');
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
    updateApiKeyToggleLabel();
}

// Get API headers with API Key
function getApiHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (apiKey) {
        headers['X-OpenAI-API-Key'] = apiKey;
    }
    return headers;
}

function setupEventListeners() {
    const form = document.getElementById('course-form');
    form.addEventListener('submit', handleFormSubmit);

    const catalogMode = document.getElementById('catalog-mode');
    catalogMode.addEventListener('change', handleCatalogModeChange);

    // API Key management
    document.getElementById('save-api-key').addEventListener('click', saveApiKey);
    document.getElementById('toggle-api-key').addEventListener('click', toggleApiKeyVisibility);
    
    // Logs management
    document.getElementById('clear-logs-btn').addEventListener('click', clearLogs);

    const languageToggle = document.getElementById('language-toggle');
    if (languageToggle) {
        languageToggle.addEventListener('click', toggleLanguage);
    }

    // Mode toggle
    const modeGenerate = document.getElementById('mode-generate');
    const modeOptimize = document.getElementById('mode-optimize');
    if (modeGenerate) {
        modeGenerate.addEventListener('click', () => switchMode('generate'));
    }
    if (modeOptimize) {
        modeOptimize.addEventListener('click', () => switchMode('optimize'));
    }

    // Optimize mode
    const optimizeForm = document.getElementById('optimize-form');
    if (optimizeForm) {
        optimizeForm.addEventListener('submit', handleOptimizeSubmit);
    }

    const slidePdfFiles = document.getElementById('slide-pdf-files');
    if (slidePdfFiles) {
        slidePdfFiles.addEventListener('change', handleSlideFilesChange);
    }

    const optimizeClearLogsBtn = document.getElementById('optimize-clear-logs-btn');
    if (optimizeClearLogsBtn) {
        optimizeClearLogsBtn.addEventListener('click', () => {
            const container = document.getElementById('optimize-logs-container');
            if (container) {
                container.innerHTML = '<p class="logs-placeholder">' + t('logsPlaceholder') + '</p>';
            }
        });
    }
}

// Switch between Generate and Optimize modes
function switchMode(mode) {
    const generateSections = ['config-section', 'progress-section', 'results-section'];
    const optimizeSections = ['optimize-section', 'optimize-progress-section', 'optimize-results-section'];

    const modeGenerateBtn = document.getElementById('mode-generate');
    const modeOptimizeBtn = document.getElementById('mode-optimize');

    if (mode === 'generate') {
        modeGenerateBtn.classList.add('active');
        modeOptimizeBtn.classList.remove('active');
        generateSections.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = '';
        });
        optimizeSections.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
        // Re-hide progress/results if no task running
        if (!currentTaskId) {
            const ps = document.getElementById('progress-section');
            const rs = document.getElementById('results-section');
            if (ps) ps.style.display = 'none';
            if (rs) rs.style.display = 'none';
        }
    } else {
        modeOptimizeBtn.classList.add('active');
        modeGenerateBtn.classList.remove('active');
        generateSections.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
        // Show optimize config, hide progress/results unless running
        const os = document.getElementById('optimize-section');
        if (os) os.style.display = '';
        const ops = document.getElementById('optimize-progress-section');
        if (ops && !window.currentOptimizeTaskId) ops.style.display = 'none';
        const ors = document.getElementById('optimize-results-section');
        if (ors && !window.currentOptimizeTaskId) ors.style.display = 'none';
    }
}

async function loadCatalogs() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/catalog/list`, {
            headers: getApiHeaders()
        });
        const data = await response.json();
        
        const select = document.getElementById('catalog-select');
        select.innerHTML = '';

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.setAttribute('data-i18n', 'catalogSelectDefault');
        defaultOption.textContent = t('catalogSelectDefault');
        select.appendChild(defaultOption);
        
        data.catalogs.forEach(catalog => {
            const option = document.createElement('option');
            option.value = catalog.name;
            option.textContent = catalog.filename;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load catalogs:', error);
        const select = document.getElementById('catalog-select');
        if (select) {
            select.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.setAttribute('data-i18n', 'catalogListFailed');
            option.textContent = t('catalogListFailed');
            select.appendChild(option);
        }
    }
}

function handleCatalogModeChange(e) {
    const mode = e.target.value;
    const uploadGroup = document.getElementById('catalog-upload-group');
    const selectGroup = document.getElementById('catalog-select-group');
    const jsonGroup = document.getElementById('catalog-json-group');

    // Hide all groups first
    uploadGroup.style.display = 'none';
    selectGroup.style.display = 'none';
    jsonGroup.style.display = 'none';

    // Show relevant group
    if (mode === 'upload') {
        uploadGroup.style.display = 'block';
        jsonGroup.style.display = 'block';
    } else if (mode === 'select') {
        selectGroup.style.display = 'block';
    } else if (mode === 'default') {
        // No additional UI needed
    }
}

async function handleFormSubmit(e) {
    e.preventDefault();
    
    // Check API Key
    if (!apiKey) {
        const key = document.getElementById('api-key').value.trim();
        if (!key) {
            alert(t('alertProvideApiKey'));
            document.getElementById('api-key').focus();
            return;
        }
        saveApiKey();
        apiKey = key;
    }

    setSubmitButtonLoading(true);

    try {
        // Collect form data
        const formData = {
            course_name: document.getElementById('course-name').value,
            model_name: document.getElementById('model-name').value,
            exp_name: document.getElementById('exp-name').value || 'default',
            copilot: document.getElementById('copilot-mode').checked,
            generate_pptx: document.getElementById('pptx-mode').checked
        };

        // Handle catalog
        const catalogMode = document.getElementById('catalog-mode').value;
        if (catalogMode === 'default') {
            formData.catalog = 'default_catalog';
        } else if (catalogMode === 'select') {
            const selected = document.getElementById('catalog-select').value;
            if (selected) {
                formData.catalog = selected;
            }
        } else if (catalogMode === 'upload') {
            // Handle file upload or JSON input
            const fileInput = document.getElementById('catalog-file');
            const jsonInput = document.getElementById('catalog-json').value;

            if (fileInput.files.length > 0) {
                // Upload file first
                const uploadResponse = await uploadCatalogFile(fileInput.files[0]);
                formData.catalog = uploadResponse.filename.replace('.json', '');
            } else if (jsonInput.trim()) {
                // Use JSON input directly
                try {
                    formData.catalog_data = JSON.parse(jsonInput);
                } catch (err) {
                    alert(t('invalidCatalogJson'));
                    setSubmitButtonLoading(false);
                    return;
                }
            }
        }

        // Submit request
        const response = await fetch(`${API_BASE_URL}/api/course/generate`, {
            method: 'POST',
            headers: getApiHeaders(),
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        currentTaskId = result.task_id;
        
        // Store exp_name from form for later use
        const expNameInput = document.getElementById('exp-name');
        window.currentExpName = expNameInput ? (expNameInput.value || 'default') : 'default';

        // Show progress section
        const progressSection = document.getElementById('progress-section');
        const configSection = document.getElementById('config-section');
        const resultsSection = document.getElementById('results-section');
        
        if (!progressSection) {
            console.error('progress-section element not found!');
            alert(t('errorProgressSectionMissing'));
            return;
        }
        
        console.log('显示进度区域...');
        configSection.style.display = 'none';
        progressSection.style.display = 'block';
        resultsSection.style.display = 'none';
        
        // Force visibility (in case CSS is overriding)
        progressSection.style.visibility = 'visible';
        progressSection.style.opacity = '1';
        
        console.log('进度区域已显示，检查日志容器...');
        const logsContainer = document.getElementById('logs-container');
        if (!logsContainer) {
            console.error('logs-container element not found!');
        } else {
            console.log('日志容器已找到');
        }

        // Clear previous logs
        clearLogs();
        
        // Start polling for status
        startStatusPolling();
        
        // Start log streaming (with a small delay to ensure queue is ready)
        setTimeout(() => {
            startLogStreaming(result.task_id);
        }, 500);
        
        // Start checking for new files
        startFileChecking(result.task_id);

    } catch (error) {
        console.error('Error submitting form:', error);
        alert(t('submitFailed', { message: error.message }));
        setSubmitButtonLoading(false);
    }
}

async function uploadCatalogFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = {};
    if (apiKey) {
        headers['X-OpenAI-API-Key'] = apiKey;
    }

    const response = await fetch(`${API_BASE_URL}/api/catalog/upload`, {
        method: 'POST',
        headers: headers,
        body: formData
    });

    if (!response.ok) {
        throw new Error(t('uploadCatalogFailed'));
    }

    return await response.json();
}

function startStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }

    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/course/status/${currentTaskId}`, {
                headers: getApiHeaders()
            });
            if (!response.ok) {
                throw new Error('Failed to fetch status');
            }

            const status = await response.json();
            updateProgress(status);
            lastProgressStatus = status; // Store last status for re-application

            if (status.status === 'completed' || status.status === 'failed') {
                clearInterval(statusCheckInterval);
                stopLogStreaming();
                stopFileChecking();
                
                if (status.status === 'completed') {
                    await loadResults();
                } else {
                    showError(status.error || t('taskFailedFallback'));
                }
            }
        } catch (error) {
            console.error('Error polling status:', error);
        }
    }, 2000); // Poll every 2 seconds
}

function startLogStreaming(taskId) {
    // Close existing connection if any
    stopLogStreaming();
    
    // Use fetch with ReadableStream for SSE (supports custom headers)
    const url = `${API_BASE_URL}/api/course/logs/${taskId}/stream`;
    
    console.log('Starting log stream for task:', taskId);
    console.log('Log stream URL:', url);
    appendLog(t('logConnecting'), 'info');
    
    // Create abort controller for cleanup
    const abortController = new AbortController();
    logEventSource = abortController; // Store controller for cleanup
    
    fetch(url, {
        method: 'GET',
        headers: getApiHeaders(),
        signal: abortController.signal
    }).then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        console.log('Log stream connected, status:', response.status);
        
        if (!response.body) {
            console.error('Response body is null!');
            appendLog(t('logEmptyResponse'), 'error');
            return;
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let messageCount = 0;
        let lastActivity = Date.now();
        
        function readStream() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    console.log('Log stream ended');
                    appendLog(t('logStreamEnded'), 'info');
                    return;
                }
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.trim() === '') continue; // Skip empty lines
                    
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            messageCount++;
                            
                            if (data.type === 'log') {
                                appendLog(data.message);
                                lastActivity = Date.now();
                            } else if (data.type === 'connected') {
                                appendLog(t('logConnected'), 'success');
                                console.log('Received connected message');
                            } else if (data.type === 'complete') {
                                appendLog(`\n${t('logTaskCompleted')}`, 'success');
                                stopLogStreaming();
                            } else if (data.type === 'error') {
                                appendLog(t('logErrorMessage', { message: data.message }), 'error');
                            }
                            // Ignore heartbeat messages (no need to display)
                        } catch (e) {
                            // If parsing fails, try to display raw line for debugging
                            console.warn('Failed to parse log line:', line, e);
                            if (line.trim().length > 6) {
                                appendLog(t('logParseError', { content: line.substring(0, 100) }), 'error');
                            }
                        }
                    } else if (line.trim()) {
                        // If it doesn't start with 'data: ', log it for debugging
                        console.warn('Unexpected log line format:', line.substring(0, 100));
                    }
                }
                
                // Continue reading
                readStream();
                
                // Check for inactivity (debugging)
                if (Date.now() - lastActivity > 10000 && messageCount === 0) {
                    console.warn('No messages received for 10 seconds');
                    appendLog(t('logInactivityWarning'), 'error');
                }
            }).catch(error => {
                if (error.name !== 'AbortError') {
                    console.error('Log stream read error:', error);
                    appendLog(t('logReadError', { message: error.message }), 'error');
                    appendLog(t('logReconnecting'), 'info');
                    // Try to reconnect after a delay
                    setTimeout(() => {
                        if (currentTaskId === taskId) {
                            startLogStreaming(taskId);
                        }
                    }, 3000);
                }
            });
        }
        
        readStream();
    }).catch(error => {
        if (error.name !== 'AbortError') {
            console.error('Failed to start log stream:', error);
            appendLog(t('logConnectFailed', { message: error.message }), 'error');
            appendLog(t('logCheckService'), 'info');
        }
    });
}

function stopLogStreaming() {
    if (logEventSource && logEventSource.abort) {
        logEventSource.abort();
        logEventSource = null;
    }
}

function appendLog(message, type = 'info') {
    const logsContainer = document.getElementById('logs-container');
    if (!logsContainer) {
        console.error('❌ Logs container not found!');
        console.error('尝试查找的元素 ID: logs-container');
        console.error('当前页面元素:', document.querySelectorAll('[id*="log"]'));
        return;
    }
    
    // Ensure logs section is visible
    const logsSection = document.getElementById('logs-section');
    if (logsSection) {
        logsSection.style.display = 'block';
    }
    
    const progressSection = document.getElementById('progress-section');
    if (progressSection) {
        progressSection.style.display = 'block';
    }
    
    const placeholder = logsContainer.querySelector('.logs-placeholder');
    if (placeholder) {
        placeholder.remove();
    }
    
    // Handle multi-line messages
    const lines = message.split('\n');
    lines.forEach((line, index) => {
        if (line.trim() || index === 0) {
            const logLine = document.createElement('div');
            logLine.className = `log-line log-${type}`;
            logLine.textContent = line;
            logsContainer.appendChild(logLine);
        }
    });
    
    // Auto-scroll to bottom
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function clearLogs() {
    const logsContainer = document.getElementById('logs-container');
    if (!logsContainer) {
        return;
    }
    logsContainer.innerHTML = '';
    const placeholder = document.createElement('p');
    placeholder.className = 'logs-placeholder';
    placeholder.setAttribute('data-i18n', 'logsPlaceholder');
    placeholder.textContent = t('logsPlaceholder');
    logsContainer.appendChild(placeholder);
}

function startFileChecking(taskId) {
    // Clear previous known files
    knownFiles.clear();
    
    // Stop any existing file checking
    stopFileChecking();
    
    // Check for files every 3 seconds
    fileCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/course/results/${taskId}/files`, {
                headers: getApiHeaders()
            });
            
            if (!response.ok) {
                return; // Silently fail, will retry
            }
            
            const data = await response.json();
            updateFileList(data.files || [], data.status);
            
        } catch (error) {
            console.error('Error checking files:', error);
        }
    }, 3000); // Check every 3 seconds
    
    // Do an immediate check
    setTimeout(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/course/results/${taskId}/files`, {
                headers: getApiHeaders()
            });
            if (response.ok) {
                const data = await response.json();
                updateFileList(data.files || [], data.status);
            }
        } catch (error) {
            console.error('Error in initial file check:', error);
        }
    }, 1000);
}

function stopFileChecking() {
    if (fileCheckInterval) {
        clearInterval(fileCheckInterval);
        fileCheckInterval = null;
    }
}

function updateFileList(files, taskStatus) {
    // Show results section if not already visible
    const resultsSection = document.getElementById('results-section');
    if (files.length > 0 && resultsSection.style.display === 'none') {
        resultsSection.style.display = 'block';
    }
    
    // Check for new files before updating knownFiles
    const newFiles = files.filter(file => {
        const fileKey = `${file.path}`;
        return !knownFiles.has(fileKey);
    });
    
    // Add new files to knownFiles
    newFiles.forEach(file => {
        knownFiles.add(file.path);
    });
    
    // Always update display if there are files or if status changed
    if (files.length > 0 || taskStatus === 'completed') {
        displayFiles(files, taskStatus, newFiles);
        
        // Notify user about new files
        if (newFiles.length > 0 && taskStatus === 'running') {
            const fileNames = newFiles.map(f => f.name).join(', ');
            appendLog(t('logNewFiles', { fileNames }), 'success');
        }
    }
}

function displayFiles(files, taskStatus, newFiles = [], expName = null) {
    const resultsContent = document.getElementById('results-content');
    
    if (files.length === 0) {
        resultsContent.innerHTML = `<p>${t('resultsNone')}</p>`;
        return;
    }
    
    // Get exp_name from parameter, window variable, or extract from path
    if (!expName) {
        expName = window.currentExpName || 'default';
    }
    if (expName === 'default' && files.length > 0 && files[0].path) {
        // Try to extract exp name from path (e.g., "exp/test/chapter_1/file.md" -> "test")
        const pathParts = files[0].path.split('/');
        if (pathParts.length > 1 && pathParts[0] === 'exp') {
            expName = pathParts[1];
        }
    }
    
    // Get absolute path based on current location
    // For file:// protocol, use the directory structure
    let absolutePath;
    if (window.location.protocol === 'file:') {
        // Extract base path from current file location
        const currentPath = window.location.pathname;
        const basePath = currentPath.substring(0, currentPath.lastIndexOf('/frontend/'));
        absolutePath = `${basePath}/exp/${expName}`;
    } else {
        // For http://, use relative path
        absolutePath = `exp/${expName}`;
    }
    
    // For macOS, convert to absolute path
    // Try to detect if we're in the project directory
    const projectPath = '/Users/harris/PycharmProjects/instructional_agents';
    const fullPath = `${projectPath}/exp/${expName}`;
    
    // Create a set of new file paths for quick lookup
    const newFilePaths = new Set(newFiles.map(f => f.path));
    
    const ROOT_DIR_KEY = '__ROOT__';
    const fileGroups = {};
    files.forEach(file => {
        const dir = file.path && file.path.includes('/') ? file.path.substring(0, file.path.lastIndexOf('/')) : ROOT_DIR_KEY;
        if (!fileGroups[dir]) {
            fileGroups[dir] = [];
        }
        fileGroups[dir].push(file);
    });

    let html = '';

    if (taskStatus === 'running') {
        html += `<p class="success-message">${t('resultsGenerating')}</p>`;
    } else if (taskStatus === 'completed') {
        html += `<p class="success-message">${t('resultsCompleted', { count: files.length })}</p>`;
    }

    html += `
        <div class="file-location-info" style="background: #f0f9ff; border: 1px solid #3b82f6; border-radius: 6px; padding: 15px; margin: 15px 0;">
            <h3 style="margin: 0 0 10px 0; color: #1e40af; font-size: 1rem;">${t('fileLocationTitle')}</h3>
            <div style="margin-bottom: 10px;">
                <strong>${t('fileLocationPathLabel')}</strong>
                <code style="background: white; padding: 4px 8px; border-radius: 4px; font-size: 0.9em; word-break: break-all; display: block; margin-top: 5px;">
                    ${fullPath}
                </code>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="copyPath('${fullPath}')" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.875rem;">
                    ${t('fileLocationCopy')}
                </button>
                <a href="file://${fullPath}" target="_blank" class="btn btn-primary" style="padding: 6px 12px; font-size: 0.875rem; text-decoration: none; display: inline-block;">
                    ${t('fileLocationOpen')}
                </a>
                <button onclick="openInFinder('${fullPath}')" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.875rem;">
                    ${t('fileLocationFinder')}
                </button>
            </div>
            <p style="margin: 10px 0 0 0; font-size: 0.875rem; color: #6b7280;">
                ${t('fileLocationTip')}
            </p>
        </div>
    `;

    html += '<div class="file-groups">';

    const sortedDirs = Object.keys(fileGroups).sort((a, b) => {
        if (a === ROOT_DIR_KEY) return -1;
        if (b === ROOT_DIR_KEY) return 1;
        return a.localeCompare(b);
    });

    sortedDirs.forEach(dir => {
        const dirFiles = fileGroups[dir];
        html += `<div class="file-group">`;
        if (dir !== ROOT_DIR_KEY) {
            html += `<h4 class="file-group-title">📁 ${dir}</h4>`;
        }
        html += '<ul class="file-list">';

        dirFiles.forEach(file => {
            const fileSize = formatFileSize(file.size);
            const downloadUrl = `${API_BASE_URL}/api/course/results/${currentTaskId}/download/${file.path}`;
            const isNew = newFilePaths.has(file.path);
            const newBadge = isNew ? t('newBadgeLabel') : '';
            const fileTypeLabel = file.type || t('unknownFileType');

            html += `
                <li class="file-item ${isNew ? 'file-item-new' : ''}">
                    <div class="file-info">
                        <div class="file-name">
                            ${getFileIcon(file.type)} ${file.name}
                            ${newBadge}
                        </div>
                        <div class="file-meta">${fileSize} • ${fileTypeLabel}</div>
                    </div>
                    <div class="file-actions">
                        <a href="${downloadUrl}" class="btn-small" download>${t('downloadLabel')}</a>
                    </div>
                </li>
            `;
        });

        html += '</ul></div>';
    });

    html += '</div>';
    resultsContent.innerHTML = html;
}

function getFileIcon(fileType) {
    const icons = {
        '.md': '📝',
        '.tex': '📄',
        '.pdf': '📕',
        '.json': '📋',
        '.txt': '📄',
        '.py': '🐍',
        '.html': '🌐',
        '.css': '🎨',
        '.js': '⚡'
    };
    return icons[fileType] || '📄';
}

// Copy path to clipboard
function copyPath(path) {
    // Try to use modern clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(path).then(() => {
            alert(t('copyPathSuccess', { path }));
        }).catch(err => {
            console.error('Failed to copy:', err);
            fallbackCopy(path);
        });
    } else {
        fallbackCopy(path);
    }
}

function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
        alert(t('copyPathSuccess', { path: text }));
    } catch (err) {
        alert(t('copyPathFailure', { path: text }));
    }
    document.body.removeChild(textarea);
}

// Open in Finder (macOS) or Explorer (Windows)
function openInFinder(path) {
    // For macOS, try to open Finder
    if (navigator.platform.toLowerCase().includes('mac')) {
        // Try file:// URL first
        const fileUrl = `file://${path}`;
        window.open(fileUrl, '_blank');
        
        // Also try to use a hidden link click
        setTimeout(() => {
            const link = document.createElement('a');
            link.href = fileUrl;
            link.target = '_blank';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }, 100);
    } else {
        // For Windows/Linux, try file:// URL
        const fileUrl = `file://${path}`;
        window.open(fileUrl, '_blank');
    }
}

function updateProgress(status) {
    lastProgressStatus = { ...status };
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const currentStage = document.getElementById('current-stage');
    const errorMessage = document.getElementById('error-message');

    progressBar.style.width = `${status.progress}%`;
    const statusLabel = getStatusText(status.status);
    progressText.textContent = t('progressTextTemplate', { progress: status.progress, status: statusLabel });
    progressText.dataset.manual = 'true';
    
    if (status.current_stage) {
        currentStage.textContent = t('currentStageLabel', { stage: status.current_stage });
    }
    else {
        currentStage.textContent = '';
    }

    if (status.error) {
        errorMessage.textContent = t('errorLabel', { message: status.error });
        errorMessage.style.display = 'block';
    } else {
        errorMessage.style.display = 'none';
    }
}

function getStatusText(status) {
    const statusKeyMap = {
        pending: 'statusPending',
        running: 'statusRunning',
        completed: 'statusCompleted',
        failed: 'statusFailed'
    };
    const translationKey = statusKeyMap[status];
    return translationKey ? t(translationKey) : status;
}

async function loadResults() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/course/results/${currentTaskId}/files`, {
            headers: getApiHeaders()
        });
        if (!response.ok) {
            throw new Error('Failed to load results');
        }

        const data = await response.json();
        // Store exp_name for file location display
        window.currentExpName = data.exp_name || 'default';
        displayFiles(data.files || [], data.status || 'completed', data.exp_name);

        // Show results section
        document.getElementById('results-section').style.display = 'block';
    } catch (error) {
        console.error('Error loading results:', error);
        alert(t('errorLoadResults', { message: error.message }));
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function showError(message) {
    const errorMessage = document.getElementById('error-message');
    errorMessage.textContent = t('errorLabel', { message });
    errorMessage.style.display = 'block';
}

// ==================== Slide Optimization Functions ====================

let currentStorageId = null;

// Handle slide files selection
function handleSlideFilesChange(e) {
    const files = Array.from(e.target.files);
    const filesList = document.getElementById('slide-files-list');

    if (files.length === 0) {
        filesList.innerHTML = '';
        return;
    }

    let html = '<div style="margin-top: 10px;"><strong>已选择的文件：</strong><ul style="margin: 5px 0; padding-left: 20px;">';
    files.forEach(file => {
        html += `<li>📄 ${escapeHtml(file.name)} (${formatFileSize(file.size)})</li>`;
    });
    html += '</ul></div>';
    filesList.innerHTML = html;
}

// Handle optimize form submission (new unified optimize mode)
async function handleOptimizeSubmit(e) {
    e.preventDefault();

    if (!apiKey) {
        const key = document.getElementById('api-key').value.trim();
        if (!key) {
            alert(t('alertProvideApiKey'));
            document.getElementById('api-key').focus();
            return;
        }
        saveApiKey();
        apiKey = key;
    }

    const filesInput = document.getElementById('slide-pdf-files');
    const files = Array.from(filesInput.files);

    if (files.length === 0) {
        alert(t('slideNoFilesSelected') || 'Please select PDF files');
        return;
    }

    const userRequirements = document.getElementById('user-requirements').value.trim();
    if (!userRequirements) {
        alert('Please provide optimization requirements');
        return;
    }

    const modelName = document.getElementById('optimize-model-name').value;
    const expName = document.getElementById('optimize-exp-name').value.trim() || 'default';
    const chapterName = document.getElementById('chapter-name').value.trim() || null;
    const modeSelect = document.getElementById('optimize-mode-select');
    const mode = modeSelect ? modeSelect.value : 'regenerate';

    const submitBtn = document.getElementById('optimize-submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>⏳</span><span>处理中...</span>';

    try {
        // Step 1: Upload PDF files
        const uploadStatus = document.getElementById('slide-upload-status');
        uploadStatus.style.display = 'block';
        uploadStatus.querySelector('.upload-status-message').textContent = 'Uploading PDF files...';

        const storageId = await uploadOptimizeFiles(files);

        uploadStatus.querySelector('.upload-status-message').innerHTML =
            '<span style="color: green;">Upload complete (' + files.length + ' files)</span>';

        // Step 2: Start optimization task (background)
        const response = await fetch(`${API_BASE_URL}/api/optimize/start`, {
            method: 'POST',
            headers: getApiHeaders(),
            body: JSON.stringify({
                storage_id: storageId,
                user_requirements: userRequirements,
                model_name: modelName,
                exp_name: expName,
                chapter_name: chapterName,
                mode: mode
            })
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Start failed' }));
            throw new Error(error.detail || 'Failed to start optimization');
        }

        const result = await response.json();
        window.currentOptimizeTaskId = result.task_id;

        // Step 3: Show progress section and start polling + SSE
        const progressSection = document.getElementById('optimize-progress-section');
        progressSection.style.display = 'block';
        progressSection.scrollIntoView({ behavior: 'smooth' });

        startOptimizePolling(result.task_id, expName);
        startOptimizeLogStream(result.task_id);

    } catch (error) {
        console.error('Optimize error:', error);
        alert('Optimization failed: ' + error.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>🔧</span><span>开始优化</span>';
    }
}

// Upload PDF files for optimization
async function uploadOptimizeFiles(files) {
    const formData = new FormData();
    files.forEach(file => {
        formData.append('files', file);
    });

    const headers = {};
    if (apiKey) {
        headers['X-OpenAI-API-Key'] = apiKey;
    }

    const response = await fetch(`${API_BASE_URL}/api/optimize/upload`, {
        method: 'POST',
        headers: headers,
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(error.detail || 'Failed to upload PDF files');
    }

    const result = await response.json();
    return result.storage_id;
}

// Poll optimization task status
function startOptimizePolling(taskId, expName) {
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/optimize/status/${taskId}`, {
                headers: getApiHeaders()
            });
            if (!response.ok) return;

            const status = await response.json();

            // Update progress bar
            const progressBar = document.getElementById('optimize-progress-bar');
            const progressText = document.getElementById('optimize-progress-text');
            const stageText = document.getElementById('optimize-current-stage');

            if (progressBar) progressBar.style.width = status.progress + '%';
            if (progressText) progressText.textContent = status.progress + '%';
            if (stageText) stageText.textContent = status.current_stage || '';

            if (status.status === 'completed') {
                clearInterval(pollInterval);
                if (progressText) progressText.textContent = 'Completed!';

                // Load results
                loadOptimizeResults(taskId, expName);
            } else if (status.status === 'failed') {
                clearInterval(pollInterval);
                const errorDiv = document.getElementById('optimize-error-message');
                if (errorDiv) {
                    errorDiv.style.display = 'block';
                    errorDiv.textContent = 'Error: ' + (status.error || 'Unknown error');
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

// Stream optimization logs via SSE
function startOptimizeLogStream(taskId) {
    const logsContainer = document.getElementById('optimize-logs-container');
    if (!logsContainer) return;

    logsContainer.innerHTML = '';

    const eventSource = new EventSource(`${API_BASE_URL}/api/optimize/logs/${taskId}/stream`);

    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                const logLine = document.createElement('div');
                logLine.className = 'log-line';
                logLine.textContent = data.message;
                logsContainer.appendChild(logLine);
                logsContainer.scrollTop = logsContainer.scrollHeight;
            } else if (data.type === 'complete') {
                eventSource.close();
            }
        } catch (e) {
            console.error('Log parse error:', e);
        }
    };

    eventSource.onerror = function() {
        eventSource.close();
    };
}

// Load optimization results (file list)
async function loadOptimizeResults(taskId, expName) {
    const resultsSection = document.getElementById('optimize-results-section');
    const resultsContent = document.getElementById('optimize-results-content');

    resultsSection.style.display = 'block';

    try {
        const response = await fetch(`${API_BASE_URL}/api/optimize/results/${taskId}/files`, {
            headers: getApiHeaders()
        });
        const data = await response.json();

        if (!data.files || data.files.length === 0) {
            resultsContent.innerHTML = '<p>No files generated yet.</p>';
            return;
        }

        let html = '<ul style="list-style: none; padding: 0;">';
        data.files.forEach(file => {
            const downloadUrl = `${API_BASE_URL}/api/optimize/results/${taskId}/download/${file.path}`;
            html += `<li style="margin: 8px 0; padding: 8px; background: #f5f5f5; border-radius: 4px;">
                <a href="${downloadUrl}" target="_blank" download>📄 ${escapeHtml(file.name)}</a>
                <span style="color: #999; margin-left: 10px;">${formatFileSize(file.size)}</span>
            </li>`;
        });
        html += '</ul>';
        resultsContent.innerHTML = html;

    } catch (error) {
        resultsContent.innerHTML = '<p style="color: red;">Failed to load results: ' + error.message + '</p>';
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

