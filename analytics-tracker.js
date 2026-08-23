/**
 * Global Real-Time Visitor & Click Analytics Tracker
 * Tracks Pageviews, Device/Browser metadata, Button Clicks, Role Selections, and Interactions
 */

(function () {
  'use strict';

  const API_BASE = (window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') || window.location.protocol === 'file:')
    ? 'http://127.0.0.1:8000'
    : '';

  // 1. Session Identifier
  function getSessionId() {
    let sid = localStorage.getItem('ai_interview_sid');
    if (!sid) {
      sid = 'usr_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
      localStorage.setItem('ai_interview_sid', sid);
    }
    return sid;
  }

  // 2. Client Device & Browser Detection
  function getClientMeta() {
    const ua = navigator.userAgent || '';
    let browser = 'Chrome';
    if (ua.includes('Edg/')) browser = 'Microsoft Edge';
    else if (ua.includes('Firefox/')) browser = 'Firefox';
    else if (ua.includes('Safari/') && !ua.includes('Chrome/')) browser = 'Safari';
    else if (ua.includes('OPR/') || ua.includes('Opera/')) browser = 'Opera';

    let os = 'Windows';
    if (ua.includes('Mac OS') || ua.includes('Macintosh')) os = 'macOS';
    else if (ua.includes('Android')) os = 'Android';
    else if (ua.includes('iPhone') || ua.includes('iPad') || ua.includes('iOS')) os = 'iOS';
    else if (ua.includes('Linux')) os = 'Linux';

    let device = 'Desktop';
    if (/Mobi|Android|iPhone/i.test(ua)) device = 'Mobile';
    else if (/iPad|Tablet/i.test(ua) || (navigator.maxTouchPoints && navigator.maxTouchPoints > 2 && os === 'macOS')) device = 'Tablet';

    return {
      browser: browser,
      os: os,
      device_type: device,
      screen_resolution: `${window.screen.width}x${window.screen.height}`
    };
  }

  // 3. Track Page View
  function trackPageView() {
    const sid = getSessionId();
    const meta = getClientMeta();
    const pageUrl = window.location.pathname.split('/').pop() || 'index.html';

    const payload = {
      session_id: sid,
      page_url: pageUrl,
      page_title: document.title || pageUrl,
      referrer: document.referrer || 'Direct Visit',
      browser: meta.browser,
      os: meta.os,
      device_type: meta.device_type,
      screen_resolution: meta.screen_resolution
    };

    // Send to backend / Vercel Serverless Function
    const trackEndpoint = API_BASE ? `${API_BASE}/api/analytics/track` : '/api/track';
    fetch(trackEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(err => {
      // Local fallback storage for offline preview
      saveLocalAnalytics('pageviews', payload);
    });
  }

  // 4. Extract Action Type & Target Role from Click
  function inferClickMetadata(el) {
    const text = (el.innerText || el.textContent || el.value || '').trim();
    const id = el.id || '';
    const cls = el.className || '';
    const href = el.getAttribute('href') || '';
    let actionType = 'general_click';
    let targetRole = null;

    const lowerText = text.toLowerCase();
    const lowerId = id.toLowerCase();

    // Role preset detection
    if (/ux designer|user experience/i.test(text)) targetRole = 'UX Designer';
    else if (/product designer/i.test(text)) targetRole = 'Product Designer';
    else if (/ui\/ux|visual designer/i.test(text)) targetRole = 'UI/UX Designer';
    else if (/frontend|react/i.test(text)) targetRole = 'Frontend Developer';
    else if (/backend|python|fastapi/i.test(text)) targetRole = 'Backend Developer';
    else if (/genai|llm|ai engineer/i.test(text)) targetRole = 'GenAI Engineer';

    if (targetRole || cls.includes('preset') || cls.includes('chip')) {
      actionType = 'role_preset_click';
    } else if (lowerId.includes('synthesize') || lowerId.includes('generate') || lowerText.includes('synthesize') || lowerText.includes('generate') || lowerText.includes('regenerate')) {
      actionType = 'generate_questions_click';
    } else if (lowerText.includes('copy') || lowerId.includes('copy')) {
      actionType = 'copy_questions_click';
    } else if (lowerText.includes('email') || lowerId.includes('email')) {
      actionType = 'email_package_click';
    } else if (lowerText.includes('linkedin') || lowerId.includes('linkedin')) {
      actionType = 'linkedin_share_click';
    } else if (lowerText.includes('share') || lowerId.includes('share')) {
      actionType = 'share_modal_click';
    } else if (el.tagName === 'A' || href) {
      actionType = 'navigation_link_click';
    } else if (el.tagName === 'SELECT') {
      actionType = 'dropdown_select';
    }

    return {
      actionType: actionType,
      targetRole: targetRole,
      cleanText: text.length > 50 ? text.substring(0, 50) + '...' : text
    };
  }

  // 5. Track Click Event
  function trackClick(e) {
    const target = e.target.closest('button, a, select, .preset-tag, .chip, .r-btn, .btn, .stat-card, input[type="button"]');
    if (!target) return;

    const sid = getSessionId();
    const meta = getClientMeta();
    const pageUrl = window.location.pathname.split('/').pop() || 'index.html';
    const clickMeta = inferClickMetadata(target);

    const payload = {
      session_id: sid,
      page_url: pageUrl,
      element_tag: target.tagName,
      element_id: target.id || '',
      element_text: clickMeta.cleanText,
      element_class: typeof target.className === 'string' ? target.className : '',
      target_role: clickMeta.targetRole,
      action_type: clickMeta.actionType,
      browser: meta.browser,
      os: meta.os,
      device_type: meta.device_type
    };

    const clickEndpoint = API_BASE ? `${API_BASE}/api/analytics/click` : '/api/track';

    // Use sendBeacon if available, otherwise fetch
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(clickEndpoint, blob);
    } else {
      fetch(clickEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(err => {
        saveLocalAnalytics('clicks', payload);
      });
    }

    // Save to local feed for real-time visual inspection
    saveLocalAnalytics('clicks', payload);
  }

  function saveLocalAnalytics(type, data) {
    try {
      const key = 'ai_interview_local_' + type;
      let list = JSON.parse(localStorage.getItem(key) || '[]');
      data.timestamp = new Date().toISOString();
      list.unshift(data);
      if (list.length > 50) list = list.slice(0, 50);
      localStorage.setItem(key, JSON.stringify(list));
    } catch (e) {}
  }

  // Universal Page Router (works on both http:// server and file:// protocols)
  window.navTo = function (htmlPage, e) {
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
    if (window.location.protocol === 'file:') {
      window.location.href = htmlPage;
    } else {
      const routes = {
        'Dashboard.html': '/candidate/dashboard',
        'Interview-studio.html': '/candidate/interview-studio',
        'Mock-interview.html': '/candidate/mock-interview',
        'Resume-match.html': '/candidate/resume-match',
        'Interview history.html': '/candidate/history',
        'scorecard.html': '/scorecard',
        'Company-playbooks.html': '/candidate/company-playbooks',
        'Analytics.html': '/analytics',
        'Upgrade-pro.html': '/upgrade-pro',
        'Candidate-login.html': '/candidate/login',
        'Login.html': '/login',
        'Admin.html': '/admin'
      };
      const cleanName = decodeURIComponent((htmlPage || '').split('/').pop().split('?')[0].split('#')[0]);
      window.location.href = routes[cleanName] || (htmlPage.startsWith('/') ? htmlPage : '/' + htmlPage);
    }
  };

  // Dynamic Candidate Menu Fetcher & Sidebar Filter
  async function loadDynamicCandidateSidebar() {
    if (window.location.pathname.startsWith('/admin')) return;
    
    let enabledMenus = null;
    try {
      const headers = { 'Content-Type': 'application/json' };
      const primaryEndpoint = API_BASE ? `${API_BASE}/public/menus` : '/public/menus';
      const fallbackEndpoint = API_BASE ? `${API_BASE}/api/public/menus` : '/api/public/menus';

      let res = await fetch(primaryEndpoint + '?t=' + Date.now(), {
        method: 'GET',
        headers: headers,
        credentials: 'include'
      });

      if (!res.ok) {
        res = await fetch(fallbackEndpoint + '?t=' + Date.now(), {
          method: 'GET',
          headers: headers,
          credentials: 'include'
        });
      }

      if (res.ok) {
        const data = await res.json();
        enabledMenus = data.menus || [];
      }
    } catch (err) {
      console.warn('[Dynamic Menu] Error fetching public menus:', err);
    }

    if (!enabledMenus || !Array.isArray(enabledMenus)) {
      return;
    }

    const enabledRoutes = enabledMenus.map(m => (m.route || '').toLowerCase());
    const enabledNames = enabledMenus.map(m => (m.name || m.label || '').toLowerCase());

    // Filter sidebar navigation links
    const links = document.querySelectorAll('.nav-link, aside a, .sidebar a, nav a');
    links.forEach(link => {
      const href = (link.getAttribute('href') || '').toLowerCase();
      const text = (link.innerText || link.textContent || '').toLowerCase().trim();
      const cleanHref = href.split('/').pop().split('?')[0].split('#')[0];

      if (!href || href === 'javascript:void(0)' || href.startsWith('#')) {
        const isMatch = enabledNames.some(n => n && (text.includes(n) || n.includes(text)));
        if (!isMatch && (text.includes('model') || text.includes('settings'))) {
          link.style.display = 'none';
        } else {
          link.style.display = '';
        }
        return;
      }

      const isMatch = enabledRoutes.some(r => r && (r === cleanHref || cleanHref.includes(r) || r.includes(cleanHref))) ||
                      enabledNames.some(n => n && (text.includes(n) || n.includes(text)));

      if (!isMatch && (cleanHref.endsWith('.html') || href.startsWith('/candidate/'))) {
        link.style.display = 'none';
      } else {
        link.style.display = '';
      }
    });

    // Hide empty section headers (.side-label) if all links under that nav section are hidden
    document.querySelectorAll('.side-label').forEach(label => {
      const nextNav = label.nextElementSibling;
      if (nextNav && (nextNav.classList.contains('nav') || nextNav.tagName.toLowerCase() === 'nav')) {
        const visibleLinks = Array.from(nextNav.querySelectorAll('.nav-link')).filter(l => l.style.display !== 'none');
        if (visibleLinks.length === 0) {
          label.style.display = 'none';
          nextNav.style.display = 'none';
        } else {
          label.style.display = '';
          nextNav.style.display = '';
        }
      }
    });

    // Also sync dashboard cards for disabled features
    const cards = document.querySelectorAll('.grid-3 .card, .card');
    cards.forEach(card => {
      const cardLink = card.querySelector('a[href]');
      if (cardLink) {
        const href = (cardLink.getAttribute('href') || '').toLowerCase();
        const cleanHref = href.split('/').pop().split('?')[0].split('#')[0];
        if (cleanHref.endsWith('.html') || href.startsWith('/candidate/')) {
          const isMatch = enabledRoutes.some(r => r && (r === cleanHref || cleanHref.includes(r) || r.includes(cleanHref)));
          if (!isMatch) {
            card.style.display = 'none';
          } else {
            card.style.display = '';
          }
        }
      }
    });
  }

  // Initialize listeners
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      trackPageView();
      loadDynamicCandidateSidebar();
    });
  } else {
    trackPageView();
    loadDynamicCandidateSidebar();
  }

  document.addEventListener('click', function (e) {
    const a = e.target.closest('a[href]');
    if (a) {
      const href = a.getAttribute('href');
      if (href && !href.startsWith('#') && !href.startsWith('javascript:') && !href.startsWith('http://') && !href.startsWith('https://')) {
        const cleanName = decodeURIComponent(href.split('/').pop().split('?')[0].split('#')[0]);
        if (cleanName.endsWith('.html') || routesMap[cleanName]) {
          e.preventDefault();
          window.navTo(cleanName);
          return;
        }
      }
    }
    trackClick(e);
  }, { capture: true });

  const routesMap = {
    'Dashboard.html': true,
    'Interview-studio.html': true,
    'Mock-interview.html': true,
    'Resume-match.html': true,
    'Interview history.html': true,
    'scorecard.html': true,
    'Company-playbooks.html': true,
    'Analytics.html': true,
    'Upgrade-pro.html': true,
    'Candidate-login.html': true,
    'Login.html': true,
    'Admin.html': true
  };

  // Expose global tracker helper
  window.AIAnalytics = {
    getSessionId: getSessionId,
    trackCustomEvent: function (action, role, label) {
      const sid = getSessionId();
      const meta = getClientMeta();
      const payload = {
        session_id: sid,
        page_url: window.location.pathname.split('/').pop() || 'index.html',
        element_tag: 'CUSTOM',
        element_id: 'custom_event',
        element_text: label || action,
        target_role: role,
        action_type: action,
        browser: meta.browser,
        os: meta.os,
        device_type: meta.device_type
      };
      fetch(`${API_BASE}/api/analytics/click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).catch(() => {});
    }
  };
})();
