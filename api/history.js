// Vercel Serverless Function: api/history.js
// Provides question paper history records and allows deletion

const SAMPLE_HISTORY = [
  {
    id: 1,
    role: "Senior UX Designer",
    experience: "5 Years",
    difficulty: "Hard",
    skills: ["Figma", "Design Systems", "User Research", "WCAG 2.2", "Usability Testing"],
    created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    questions: [
      "How do you establish typographic scale, 8pt spatial grid, and color contrast tokens in Figma Variables for a multi-brand design system?",
      "Describe your methodology for conducting unmoderated remote usability testing on an interactive Figma checkout prototype to isolate friction points.",
      "How do you evaluate and defend WCAG 2.2 Level AA accessibility compliance against aggressive marketing aesthetics or engineering deadline cuts?",
      "Explain how you architect component variants, boolean properties, and nested instances to maximize reuse across distributed cross-functional squads.",
      "Scenario: Post-launch analytics indicate a 35% abandonment rate at step 2 of an onboarding wizard. Walk through your systematic diagnostic and iteration plan."
    ]
  },
  {
    id: 2,
    role: "Product Designer",
    experience: "5 Years",
    difficulty: "Hard",
    skills: ["Product Strategy", "UX Discovery", "Conversion Optimization", "Figma", "Metrics"],
    created_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
    questions: [
      "How do you balance aggressive business conversion targets with customer friction when redesigning a SaaS subscription upgrade flow?",
      "Describe how you define North Star product metrics and secondary guardrail indicators before launching a core feature redesign.",
      "Walk through how you would facilitate an MVP scoping workshop with cross-functional PM and Engineering leads to align on trade-offs."
    ]
  },
  {
    id: 3,
    role: "Staff Frontend Developer",
    experience: "8+ Years",
    difficulty: "Brutal",
    skills: ["React 19", "Next.js App Router", "TypeScript", "Performance", "a11y"],
    created_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    questions: [
      "Explain how you architect Server Components vs Client Components in React 19 / Next.js to minimize client bundle size and optimize TTFB.",
      "How do you diagnose and eliminate long tasks and Interaction to Next Paint (INP) bottlenecks using Chrome DevTools Performance Profiler?",
      "Describe your strategy for state orchestration: when do you use URL search params, React Context, TanStack Query, and Zustand?"
    ]
  },
  {
    id: 4,
    role: "GenAI & RAG Systems Engineer",
    experience: "5 Years",
    difficulty: "Hard",
    skills: ["LLMs", "RAG Architecture", "Vector DBs", "LangGraph", "Hallucination Evaluation"],
    created_at: new Date(Date.now() - 48 * 3600 * 1000).toISOString(),
    questions: [
      "How do you architect an enterprise hybrid vector search pipeline combining dense embeddings (text-embedding-3-large) and BM25 sparse lexical search?",
      "Describe how you evaluate retrieval precision, context recall, and hallucination rates in production using Ragas and DeepEval.",
      "How do you enforce document-level Access Control Lists (ACLs) and tenant metadata filtering in Pinecone/Milvus retrieval pipelines?"
    ]
  }
];

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,DELETE');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method === 'DELETE') {
    return res.status(200).json({ success: true, message: 'Record deleted successfully' });
  }

  return res.status(200).json(SAMPLE_HISTORY);
}
