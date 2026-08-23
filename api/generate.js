// Vercel Serverless Function: api/generate.js
// Live AI Interview Question Generation powered by Google Gemini 2.5 Flash

export default async function handler(req, res) {
  // 1. CORS Headers Setup
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );

  // Handle preflight OPTIONS request
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // 2. Method Validation
  if (req.method !== 'POST') {
    return res.status(405).json({
      error: 'Method Not Allowed',
      message: `HTTP method ${req.method} is not supported. Use POST.`
    });
  }

  // 3. Extract & Normalize Payload
  const body = req.body || {};
  const role = body.role || 'Senior Software Engineer';
  const experience = body.experience || '3-5 Years';
  const difficulty = body.difficulty || 'Hard';
  const rawSkills = body.skills || [];
  const skillsList = Array.isArray(rawSkills) ? rawSkills.join(', ') : rawSkills;
  const count = Number(body.questionCount || body.number_of_questions || 5);
  const customQuestion = body.custom_question || body.customQuestion || '';

  // 4. Validate API Key
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error('Missing GEMINI_API_KEY in environment variables.');
    return res.status(500).json({
      error: 'Configuration Error',
      message: 'GEMINI_API_KEY environment variable is not configured in Vercel settings.'
    });
  }

  // 5. Construct Prompt for Structured JSON Generation
  const systemInstruction = `You are a Principal Engineering Bar-Raiser and Technical Assessment Lead conducting high-standard job interviews.
Generate exactly ${count} highly technical, role-specific, and deep-probing interview questions for the specified candidate profile.
Difficulty level: ${difficulty}. Target Role: ${role}. Required Stack: ${skillsList}. Experience Level: ${experience}.
${customQuestion ? `Focus Topic / Custom Question Seed: "${customQuestion}". Include related probing questions branching from this seed.` : ''}

You MUST respond ONLY with a valid JSON object matching this schema:
{
  "role": "${role}",
  "difficulty": "${difficulty}",
  "experience": "${experience}",
  "skills": ["${Array.isArray(rawSkills) ? rawSkills.join('", "') : rawSkills}"],
  "questions": [
    "Question 1 text...",
    "Question 2 text..."
  ],
  "questions_details": [
    {
      "id": 1,
      "question": "Question 1 text...",
      "category": "Technical Architecture | Problem Solving | Behavioral | System Design",
      "model_answer": "Key evaluation criteria, architecture trade-offs, and expected candidate insights..."
    }
  ]
}`;

  const requestPayload = {
    contents: [
      {
        parts: [
          {
            text: `Generate ${count} ${difficulty} interview questions for ${role} with skills in ${skillsList}.`
          }
        ]
      }
    ],
    systemInstruction: {
      parts: [
        {
          text: systemInstruction
        }
      ]
    },
    generationConfig: {
      temperature: 0.7,
      topK: 40,
      topP: 0.95,
      responseMimeType: "application/json"
    }
  };

  try {
    // 6. Call Google Gemini API (gemini-2.5-flash endpoint)
    const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
    
    let geminiRes = await fetch(geminiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestPayload)
    });

    // Fallback to gemini-1.5-flash if 2.5 is not yet accessible with the key
    if (!geminiRes.ok) {
      console.warn(`Gemini 2.5 Flash returned status ${geminiRes.status}. Attempting fallback to gemini-1.5-flash...`);
      const fallbackUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;
      geminiRes = await fetch(fallbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload)
      });
    }

    if (!geminiRes.ok) {
      const errText = await geminiRes.text();
      console.error('Gemini API Error Response:', errText);
      return res.status(500).json({
        error: 'Gemini API Error',
        message: `Google Gemini API returned status ${geminiRes.status}.`,
        details: errText
      });
    }

    const geminiData = await geminiRes.json();
    const rawText = geminiData.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!rawText) {
      throw new Error('Empty response content received from Gemini model.');
    }

    // 7. Clean and parse JSON output
    let parsedOutput;
    try {
      const cleanJson = rawText.replace(/```json\s*|\s*```/g, '').trim();
      parsedOutput = JSON.parse(cleanJson);
    } catch (parseErr) {
      console.warn('JSON parsing fallback on raw text:', parseErr.message);
      parsedOutput = {
        role: role,
        difficulty: difficulty,
        questions: rawText.split('\n').filter(line => line.trim().length > 10).slice(0, count)
      };
    }

    // Ensure questions array exists
    if (!Array.isArray(parsedOutput.questions) || parsedOutput.questions.length === 0) {
      if (Array.isArray(parsedOutput.questions_details)) {
        parsedOutput.questions = parsedOutput.questions_details.map(q => q.question || q);
      } else {
        parsedOutput.questions = [
          `How do you design, optimize, and secure ${role} architecture using ${skillsList}?`,
          `Describe how you diagnose and resolve complex production latency and memory bottlenecks in ${skillsList}.`,
          `Walk through your approach to testing, continuous integration, and WCAG accessibility standards for ${role}.`
        ].slice(0, count);
      }
    }

    // Return successful structured JSON
    return res.status(200).json({
      success: true,
      role: parsedOutput.role || role,
      experience: experience,
      difficulty: parsedOutput.difficulty || difficulty,
      skills: Array.isArray(rawSkills) ? rawSkills : [rawSkills],
      count: parsedOutput.questions.length,
      questions: parsedOutput.questions,
      questions_details: parsedOutput.questions_details || [],
      model: 'gemini-2.5-flash'
    });

  } catch (error) {
    console.error('Serverless Function Exception in /api/generate:', error);
    return res.status(500).json({
      error: 'Internal Server Error',
      message: error.message || 'An unexpected error occurred during AI question synthesis.'
    });
  }
}
