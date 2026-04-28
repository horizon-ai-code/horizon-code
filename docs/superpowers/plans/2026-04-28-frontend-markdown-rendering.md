# Frontend Markdown Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Markdown rendering in the terminal and insights panel to properly display the human-readable agent outputs sent by the backend.

**Architecture:** We will install `react-markdown` and `remark-gfm` to handle Markdown rendering. We will update the `Terminal.tsx` component's `AgentTerminalLine` to use `ReactMarkdown`. We will also update the `InsightsPanel.tsx` summary section to use `ReactMarkdown` for a more consistent look.

**Tech Stack:** React, Next.js, Tailwind CSS, react-markdown, remark-gfm

---

### Task 1: Install Dependencies

- [ ] **Step 1: Install `react-markdown` and `remark-gfm`**

Run: `npm install react-markdown remark-gfm --save`
Expected: Dependencies added to `package.json`.

---

### Task 2: Update Terminal Component

**Files:**
- Modify: `src/components/features/terminal/Terminal.tsx`

- [ ] **Step 1: Import ReactMarkdown and RemarkGFM**

```typescript
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
```

- [ ] **Step 2: Update `AgentTerminalLine` to render Markdown**

```tsx
const AgentTerminalLine = ({ text, colorClass, icon: Icon }: AgentTerminalLineProps) => {
  return (
    <div className="flex items-start gap-3 text-[12px] font-mono leading-relaxed shrink-0 transition-opacity">
      <div className={`mt-0.5 ${colorClass}`}><Icon size={14} /></div>
      <div className="flex-1">
        <span className={colorClass}>&gt; </span>
        <div className={`inline-block prose prose-invert prose-p:leading-relaxed prose-pre:bg-jb-bg prose-pre:p-2 prose-pre:rounded-md max-w-none text-jb-text transition-colors opacity-90
          [&_p]:mb-1 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:ml-4 [&_li]:mb-1`}>
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

### Task 3: Update Insights Panel

**Files:**
- Modify: `src/components/features/output/InsightsPanel.tsx`

- [ ] **Step 1: Import ReactMarkdown and RemarkGFM**

- [ ] **Step 2: Update Summary section to use ReactMarkdown**

Replace the manual splitting logic with a proper Markdown renderer.

```tsx
{summary.trim() && (
  <div className="mt-6 p-4 rounded-[16px] border border-border bg-secondary/30">
     <h4 className={`text-[12px] font-bold mb-4 uppercase tracking-wide ${isDark ? 'text-gray-400' : 'text-slate-500'}`}>Summary</h4>
     <div className={`prose ${isDark ? 'prose-invert' : 'prose-slate'} max-w-none text-[13px] leading-relaxed`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {summary}
        </ReactMarkdown>
     </div>
  </div>
)}
```

---

### Task 4: Fix Type Definitions (if needed)

**Files:**
- Modify: `src/types/session.ts` (if `terminalEntries.text` needs to be broader, but string is fine)

---

### Task 5: Verification

- [ ] **Step 1: Run the frontend and verify rendering**

Run: `npm run dev`
Verify: Status messages in the terminal show bold text, lists, and code blocks correctly.
Verify: Insights summary looks professional.
