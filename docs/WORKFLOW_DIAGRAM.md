# Instructional Agents System - Workflow Diagram

本文档包含系统工作流程的可视化流程图。

## 完整系统流程图

```mermaid
graph TB
    Start([系统启动]) --> Input[输入: Course Name<br/>+ Catalog Data<br/>+ Copilot Mode]
    
    Input --> Phase1[Phase 1: Foundation Phase]
    
    Phase1 --> Task1[Task 1: Instructional Goals Definition]
    Task1 --> Task1_Agents[Teaching Faculty<br/>↔<br/>Instructional Designer<br/>→<br/>Summarizer]
    Task1_Agents --> Task1_Output[Output: result_instructional_goals.md]
    
    Task1_Output --> Task2[Task 2: Resource Assessment]
    Task2 --> Task2_Agents[Teaching Faculty<br/>↔<br/>Instructional Designer<br/>→<br/>Summarizer]
    Task2_Agents --> Task2_Output[Output: result_resource_assessment.md]
    
    Task2_Output --> Task3[Task 3: Target Audience Analysis]
    Task3 --> Task3_Agents[Teaching Faculty<br/>↔<br/>Course Coordinator<br/>→<br/>Summarizer]
    Task3_Agents --> Task3_Output[Output: result_target_audience.md]
    
    Task3_Output --> Task4[Task 4: Syllabus Design]
    Task4 --> Task4_Agents[Teaching Faculty<br/>↔<br/>Instructional Designer<br/>→<br/>Summarizer]
    Task4_Agents --> Task4_Output[Output: result_syllabus_design.md]
    
    Task4_Output --> SyllabusProc[Syllabus Processing]
    SyllabusProc --> SyllabusProc_Agent[SyllabusProcessor Agent]
    SyllabusProc_Agent --> Chapters[Output: processed_chapters.json]
    
    Chapters --> Task5[Task 5: Assessment Planning]
    Task5 --> Task5_Agents[Teaching Faculty<br/>↔<br/>Instructional Designer<br/>→<br/>Summarizer]
    Task5_Agents --> Task5_Output[Output: result_assessment_planning.md]
    
    Task5_Output --> Task6[Task 6: Final Project Design]
    Task6 --> Task6_Agents[Teaching Faculty<br/>↔<br/>Instructional Designer<br/>→<br/>Summarizer]
    Task6_Agents --> Task6_Output[Output: result_final_exam_project.md]
    
    Task6_Output --> Phase2[Phase 2: Chapter Development Phase]
    
    Phase2 --> LoopStart{对每个章节}
    LoopStart --> SlidesDelib[SlidesDeliberation]
    
    SlidesDelib --> Step0[Step 0: Get Templates]
    Step0 --> Step1[Step 1: Generate Slides Outline<br/>Agent: Instructional Designer]
    Step1 --> Step2[Step 2: Generate Initial LaTeX<br/>Agent: Teaching Assistant]
    Step2 --> Step3[Step 3: Generate Script Template<br/>Agent: Teaching Assistant]
    Step3 --> Step4[Step 4: Generate Assessment Template<br/>Agent: Teaching Assistant]
    
    Step4 --> SlideLoop{对每张幻灯片}
    
    SlideLoop --> Step5_1[Step 5.1: Generate Slide Draft<br/>Agent: Teaching Faculty]
    Step5_1 --> Step5_2[Step 5.2: Generate Slide LaTeX<br/>Agent: Teaching Assistant]
    Step5_2 --> Step5_3[Step 5.3: Generate Slide Script<br/>Agent: Teaching Assistant]
    Step5_3 --> Step5_4[Step 5.4: Generate Slide Assessment<br/>Agent: Teaching Assistant]
    
    Step5_4 --> SlideLoopEnd{还有更多幻灯片?}
    SlideLoopEnd -->|是| SlideLoop
    SlideLoopEnd -->|否| Step6[Step 6: Compile LaTeX Source]
    
    Step6 --> Step7[Step 7: Compile Slides Script]
    Step7 --> Step8[Step 8: Compile Assessment]
    
    Step8 --> ChapterOutput[Chapter Output:<br/>slides.tex<br/>script.md<br/>assessment.md]
    
    ChapterOutput --> LoopEnd{还有更多章节?}
    LoopEnd -->|是| LoopStart
    LoopEnd -->|否| Compile[Final LaTeX Compilation<br/>LaTeXCompiler]
    
    Compile --> End([完成])
    
    style Phase1 fill:#e1f5ff
    style Phase2 fill:#fff4e1
    style Task1 fill:#f0f0f0
    style Task2 fill:#f0f0f0
    style Task3 fill:#f0f0f0
    style Task4 fill:#f0f0f0
    style Task5 fill:#f0f0f0
    style Task6 fill:#f0f0f0
    style SlidesDelib fill:#e8f5e9
    style Step1 fill:#fff9c4
    style Step2 fill:#fff9c4
    style Step3 fill:#fff9c4
    style Step4 fill:#fff9c4
    style Step5_1 fill:#fff9c4
    style Step5_2 fill:#fff9c4
    style Step5_3 fill:#fff9c4
    style Step5_4 fill:#fff9c4
```

## Foundation Phase详细流程图

```mermaid
graph LR
    subgraph Foundation["Foundation Phase"]
        T1[Task 1: Instructional Goals]
        T2[Task 2: Resource Assessment]
        T3[Task 3: Target Audience]
        T4[Task 4: Syllabus Design]
        T5[Task 5: Assessment Planning]
        T6[Task 6: Final Project]
        
        T1 -->|Context| T2
        T2 -->|Context| T3
        T3 -->|Context| T4
        T4 -->|Context| T5
        T5 -->|Context| T6
    end
    
    subgraph Output["Outputs"]
        O1[instructional_goals.md]
        O2[resource_assessment.md]
        O3[target_audience.md]
        O4[syllabus_design.md]
        O5[assessment_planning.md]
        O6[final_exam_project.md]
    end
    
    T1 --> O1
    T2 --> O2
    T3 --> O3
    T4 --> O4
    T5 --> O5
    T6 --> O6
    
    O4 --> SyllabusProc[SyllabusProcessor]
    SyllabusProc --> Chapters[processed_chapters.json]
```

## SlidesDeliberation详细流程图

```mermaid
graph TB
    Start([开始 SlidesDeliberation]) --> Input[输入: Chapter Info<br/>+ User Feedback<br/>+ Foundation Results]
    
    Input --> Step0[Step 0: Get Templates]
    Step0 --> Step1[Step 1: Generate Slides Outline]
    Step1 --> ID1[Instructional Designer Agent]
    ID1 --> Outline[Output: slides_outline JSON]
    
    Outline --> Step2[Step 2: Generate Initial LaTeX]
    Step2 --> TA1[Teaching Assistant Agent]
    TA1 --> LaTeX[Output: latex_dict structure]
    
    LaTeX --> Step3[Step 3: Generate Script Template]
    Step3 --> TA2[Teaching Assistant Agent]
    TA2 --> ScriptTemplate[Output: script_template JSON]
    
    ScriptTemplate --> Step4[Step 4: Generate Assessment Template]
    Step4 --> TA3[Teaching Assistant Agent]
    TA3 --> AssessTemplate[Output: assessment_template JSON]
    
    AssessTemplate --> SlideLoop{对每张幻灯片循环}
    
    SlideLoop --> Step5_1[Step 5.1: Generate Slide Draft]
    Step5_1 --> TF[Teaching Faculty Agent]
    TF --> Draft[slide_draft content]
    
    Draft --> Step5_2[Step 5.2: Generate Slide LaTeX]
    Step5_2 --> TA4[Teaching Assistant Agent]
    TA4 --> LaTeXFrames[Updated latex_dict]
    
    LaTeXFrames --> Step5_3[Step 5.3: Generate Slide Script]
    Step5_3 --> TA5[Teaching Assistant Agent]
    TA5 --> Script[Updated slides_script]
    
    Script --> Step5_4[Step 5.4: Generate Slide Assessment]
    Step5_4 --> TA6[Teaching Assistant Agent]
    TA6 --> Assessment[Updated assessment_content]
    
    Assessment --> Check{还有更多幻灯片?}
    Check -->|是| SlideLoop
    Check -->|否| Compile1[Step 6: Compile LaTeX]
    
    Compile1 --> Compile2[Step 7: Compile Script]
    Compile2 --> Compile3[Step 8: Compile Assessment]
    
    Compile3 --> Output[输出:<br/>slides.tex<br/>script.md<br/>assessment.md]
    Output --> End([结束])
    
    style Start fill:#e1f5ff
    style SlideLoop fill:#fff4e1
    style TF fill:#fff9c4
    style ID1 fill:#fff9c4
    style TA1 fill:#fff9c4
    style TA2 fill:#fff9c4
    style TA3 fill:#fff9c4
    style TA4 fill:#fff9c4
    style TA5 fill:#fff9c4
    style TA6 fill:#fff9c4
    style End fill:#e8f5e9
```

## Agent交互模式图

```mermaid
graph LR
    subgraph Deliberation["Deliberation模式"]
        A1[Agent 1] <-->|讨论| A2[Agent 2]
        A1 -->|讨论历史| Summary[Summary Agent]
        A2 -->|讨论历史| Summary
        Summary -->|生成| Output[最终输出]
    end
    
    subgraph SlidesDelib["SlidesDeliberation模式"]
        ID[Instructional Designer] -->|生成| Outline[Slides Outline]
        TF[Teaching Faculty] -->|生成| Content[Slide Content]
        TA[Teaching Assistant] -->|生成| LaTeX[LaTeX Code]
        TA -->|生成| Script[Script]
        TA -->|生成| Assess[Assessment]
    end
```

## 数据流图

```mermaid
graph TB
    Input[输入数据]
    
    subgraph Catalog["Catalog Data"]
        CS[course_structure]
        IR[institutional_requirements]
        TC[teaching_constraints]
        SP[student_profile]
        PF[prior_feedback]
        IP[instructor_preferences]
        AD[assessment_design]
    end
    
    Input --> Phase1[Foundation Phase]
    Catalog --> Phase1
    
    Phase1 --> T1_Out[Task 1 Output]
    T1_Out --> T2_Out[Task 2 Output]
    T2_Out --> T3_Out[Task 3 Output]
    T3_Out --> T4_Out[Task 4 Output]
    
    T4_Out --> SyllabusProc[Syllabus Processing]
    SyllabusProc --> Chapters[JSON Chapters]
    
    Chapters --> Phase2[Chapter Development Phase]
    T1_Out --> Phase2
    T2_Out --> Phase2
    T3_Out --> Phase2
    T4_Out --> Phase2
    
    Phase2 --> Slide1[Chapter 1 Slides]
    Phase2 --> Slide2[Chapter 2 Slides]
    Phase2 --> SlideN[Chapter N Slides]
    
    Slide1 --> Files1[slides.tex<br/>script.md<br/>assessment.md]
    Slide2 --> Files2[slides.tex<br/>script.md<br/>assessment.md]
    SlideN --> FilesN[slides.tex<br/>script.md<br/>assessment.md]
    
    style Phase1 fill:#e1f5ff
    style Phase2 fill:#fff4e1
    style SyllabusProc fill:#e8f5e9
```

## Copilot Mode流程图

```mermaid
graph TB
    Start([开始 Deliberation]) --> PreCheck{是否启用<br/>Copilot?}
    
    PreCheck -->|否| Run[运行 Deliberation]
    PreCheck -->|是| UserPre[用户提供预建议]
    
    UserPre --> Run
    Run --> Output[生成输出]
    
    Output --> PostCheck{是否启用<br/>Copilot?}
    
    PostCheck -->|否| Next[继续下一个]
    PostCheck -->|是| UserChoice{用户选择}
    
    UserChoice -->|1. 继续| Next
    UserChoice -->|2. 重新运行| UserPost[用户提供新建议]
    
    UserPost --> Accumulate[累积所有建议]
    Accumulate --> Run
    
    Next --> End([结束])
    
    style Start fill:#e1f5ff
    style UserPre fill:#fff9c4
    style UserPost fill:#fff9c4
    style Run fill:#e8f5e9
    style End fill:#e8f5e9
```

## 关键特点说明

### 1. 顺序上下文构建
每个Foundation Phase任务都使用之前所有任务的输出作为上下文，确保：
- 学习目标指导资源评估
- 资源评估影响目标受众分析
- 所有之前的输出指导大纲设计
- 大纲设计影响评估规划

### 2. 模板驱动生成
SlidesDeliberation使用分阶段模板生成：
- 先创建结构（outline, templates）
- 再填充内容（draft, LaTeX, script, assessment）
- 最后编译成最终文件

### 3. 上下文感知
- 每张幻灯片的生成都考虑相邻幻灯片
- Chapter开发考虑Foundation Phase的所有结果
- 脚本生成考虑前后幻灯片的过渡

### 4. 多Agent协作
- Foundation Phase: Teaching Faculty ↔ Instructional Designer/Course Coordinator
- SlidesDeliberation: Instructional Designer → Teaching Faculty → Teaching Assistant

---

这些流程图展示了系统从课程名称输入到完整教学材料生成的完整工作流程。每个阶段都有明确的输入输出和Agent职责分工。


