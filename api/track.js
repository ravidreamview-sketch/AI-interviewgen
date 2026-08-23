// Vercel Serverless Function: api/track.js
// Lightweight telemetry handler to record pageviews and clicks, returning HTTP 200

export default async function handler(req, res) {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,POST');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );

  // Handle preflight OPTIONS request
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // Handle incoming telemetry payload
  try {
    const payload = req.body || {};
    // Log telemetry server-side for Vercel logs observability
    if (payload.action_type || payload.page_url) {
      console.log(`📊 [Telemetry Tracked] Page: ${payload.page_url || 'unknown'} | Action: ${payload.action_type || 'view'} | Role: ${payload.target_role || 'n/a'}`);
    }

    return res.status(200).json({
      status: 'tracked',
      success: true,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error in /api/track telemetry:', error);
    return res.status(200).json({ status: 'tracked', fallback: true });
  }
}
