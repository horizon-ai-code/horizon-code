# Frontend Full Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the new backend messaging protocol (Markdown status updates and follow-up insights) into the frontend.

**Architecture:** We will install `react-markdown` for rendering agent outputs. We will update the `Terminal` component to render Markdown. We will also update the `InsightsPanel` to display the new structured insights format.

**Tech Stack:** React, Next.js, Tailwind CSS, react-markdown, remark-gfm

---

### Task 1: Update Types and Hook (Partially Done)

- [ ] **Step 1: Ensure types are updated**
(Already done in `src/types/websocket.ts`)

- [ ] **Step 2: Ensure hook is updated**
(Already done in `src/hooks/useOrchestrationSocket.tsx`)

---

### Task 2: Install Dependencies

- [ ] **Step 1: Install `react-markdown` and `remark-gfm`**

Run: `npm install react-markdown remark-gfm --save`
Expected: Dependencies added to `package.json`.

---

### Task 3: Update Terminal Component

**Files:**
- Modify: `src/components/features/terminal/Terminal.tsx`

- [ ] **Step 1: Import ReactMarkdown**

- [ ] **Step 2: Update `AgentTerminalLine` to use ReactMarkdown**

```tsx
const AgentTerminalLine = ({ text, colorClass, icon: Icon }: AgentTerminalLineProps) => {
  return (
    <div className="flex items-start gap-3 text-[12px] font-mono leading-relaxed shrink-0 transition-opacity">
      <div className={`mt-0.5 ${colorClass}`}><Icon size={14} /></div>
      <div className="flex-1">
        <span className={colorClass}>&gt; </span>
        <div className="inline-block prose prose-invert prose-p:leading-relaxed max-w-none text-jb-text transition-colors opacity-90 [&_p]:mb-1 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:ml-4 [&_li]:mb-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {text}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
};
```

---

### Task 4: Update Insights Panel

**Files:**
- Modify: `src/components/features/output/InsightsPanel.tsx`

- [ ] **Step 1: Import ReactMarkdown**

- [ ] **Step 2: Update Summary section to use ReactMarkdown**

```tsx
{summary.trim() && (
  <div className="mt-6 p-4 rounded-[16px] border border-border bg-secondary/30">
     <h4 className={`text-[12px] font-bold mb-4 uppercase tracking-wide ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>Summary</h4>
     <div className={`prose ${isDark ? 'prose-invert' : ''} max-w-none text-[13px] leading-relaxed`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {summary}
        </ReactMarkdown>
     </div>
  </div>
)}
```

---

### Task 5: Verification with Simulator

- [ ] **Step 1: Start simulation backend**
Run: `node simulate_backend.js` in a background terminal.

- [ ] **Step 2: Start frontend**
Run: `npm run dev`

- [ ] **Step 3: Trigger refactor and verify UI**
Verify that Markdown rendering works in the terminal and insights arrive correctly.
