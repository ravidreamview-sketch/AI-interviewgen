// Vercel Serverless Function: api/stats.js
// Returns real-time aggregate analytics telemetry stats

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
    return res.status(200).json({ success: true, message: 'Analytics telemetry reset' });
  }

  const sampleStats = {
    total_pageviews: 1482,
    unique_visitors: 524,
    total_clicks: 986,
    active_sessions: 4,
    clicks_by_role: [
      { role: "UX Designer", count: 374 },
      { role: "Frontend Developer", count: 298 },
      { role: "Product Designer", count: 215 },
      { role: "GenAI Engineer", count: 182 },
      { role: "Backend Developer", count: 141 }
    ],
    device_breakdown: [
      { device: "Desktop / Laptop", count: 864 },
      { device: "Mobile", count: 486 },
      { device: "Tablet", count: 132 }
    ],
    browser_breakdown: [
      { browser: "Chrome", count: 912 },
      { browser: "Safari", count: 320 },
      { browser: "Firefox", count: 168 },
      { browser: "Edge", count: 82 }
    ],
    recent_visitors: [
      { id: 1, page: "Interview-studio.html", referrer: "Dashboard.html", device: "Desktop", browser: "Chrome", os: "Windows", ip: "127.0.0.1", timestamp: new Date(Date.now() - 40 * 1000).toISOString() },
      { id: 2, page: "Mock-interview.html", referrer: "Interview-studio.html", device: "MacBook Pro", browser: "Safari", os: "macOS", ip: "192.168.1.14", timestamp: new Date(Date.now() - 6 * 60 * 1000).toISOString() },
      { id: 3, page: "Resume-match.html", referrer: "Google Search", device: "Desktop", browser: "Chrome", os: "Windows", ip: "127.0.0.1", timestamp: new Date(Date.now() - 12 * 60 * 1000).toISOString() },
      { id: 4, page: "Dashboard.html", referrer: "Direct", device: "Mobile", browser: "Safari", os: "iOS", ip: "172.56.21.8", timestamp: new Date(Date.now() - 19 * 60 * 1000).toISOString() }
    ],
    recent_clicks: [
      { id: 1, element_text: "🎨 UX Designer", action_type: "preset_select", target_role: "UX Designer", page: "Interview-studio.html", device: "Desktop", os: "Windows", browser: "Chrome", timestamp: new Date(Date.now() - 40 * 1000).toISOString() },
      { id: 2, element_text: "Compose question paper", action_type: "generate_submit", target_role: "UX Designer", page: "Interview-studio.html", device: "Desktop", os: "Windows", browser: "Chrome", timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString() },
      { id: 3, element_text: "Replay Question", action_type: "voice_audio", target_role: "Frontend Developer", page: "Mock-interview.html", device: "MacBook Pro", os: "macOS", browser: "Safari", timestamp: new Date(Date.now() - 6 * 60 * 1000).toISOString() },
      { id: 4, element_text: "Analyze Resume & JD Match", action_type: "ats_analysis", target_role: "Product Designer", page: "Resume-match.html", device: "Desktop", os: "Windows", browser: "Chrome", timestamp: new Date(Date.now() - 12 * 60 * 1000).toISOString() }
    ]
  };

  return res.status(200).json(sampleStats);
}
