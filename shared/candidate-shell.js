/**
 * RAVI GenAI Studio â€” Standardized Candidate Shell Component
 * Unified Sidebar, Navigation Hierarchy, Dynamic Profile & Authentication
 */

(function () {
  'use strict';

  const CANONICAL_NAVIGATION = [
    {
      section: 'WORKSPACE',
      items: [
        {
          key: 'dashboard',
          label: 'Dashboard',
          url: '/candidate/dashboard',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
          badge: null
        },
        {
          key: 'interview-studio',
          label: 'Generate Questions',
          url: '/candidate/interview-studio',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 2.5l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/></svg>',
          badge: null
        },
        {
          key: 'mock-interview',
          label: 'AI Mock Interview',
          url: '/candidate/mock-interview',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/></svg>',
          badge: { text: 'VIDEO + VOICE', class: 'new' }
        },
        {
          key: 'interview-coach',
          label: 'Interview Coach',
          url: '/candidate/interview-coach',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 11.5a8.38 8.38 0 0 1-9 8.5 9.2 9.2 0 0 1-4-.9L3 21l1.9-4.2A8.5 8.5 0 1 1 21 11.5Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></svg>',
          badge: { text: 'AI', class: '' }
        },
        {
          key: 'resume-match',
          label: 'Resume & JD Match',
          url: '/candidate/resume-match',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
          badge: { text: 'PRO', class: 'pro' }
        }
      ]
    },
    {
      section: 'LIBRARY',
      items: [
        {
          key: 'history',
          label: 'Interview History',
          url: '/candidate/history',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="9"/><polyline points="12 6 12 12 16 14"/></svg>',
          badge: null
        },
        {
          key: 'scorecard',
          label: 'Public Scorecards',
          url: '/scorecard',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
          badge: null
        },
        {
          key: 'company-playbooks',
          label: 'Company Playbooks',
          url: '/candidate/company-playbooks',
          iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>',
          badge: null
        }
      ]
    }
  ];

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function getInitials(name) {
    if (!name) return 'CA';
    const clean = String(name).trim().replace(/[@._-]/g, ' ');
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return 'CA';
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function formatPlanLabel(planTier) {
    const p = String(planTier || 'free').trim().toLowerCase();
    if (p === 'enterprise') return 'ENTERPRISE TIER';
    if (p === 'pro') return 'PRO TIER';
    return 'FREE TIER';
  }

  function buildSidebarHTML() {
    let sectionsHtml = '';
    CANONICAL_NAVIGATION.forEach((sec, idx) => {
      const topMargin = idx > 0 ? ' style="margin-top: 10px;"' : '';
      sectionsHtml += `<div class="side-label"${topMargin}>${escapeHtml(sec.section)}</div>`;
      sectionsHtml += `<nav class="nav" aria-label="${escapeHtml(sec.section)} Navigation">`;
      sec.items.forEach(item => {
        let badgeHtml = '';
        if (item.badge) {
          const cls = item.badge.class ? ` ${item.badge.class}` : '';
          badgeHtml = `<span class="nav-badge${cls}">${escapeHtml(item.badge.text)}</span>`;
        }
        sectionsHtml += `
          <a class="nav-link" href="${escapeHtml(item.url)}" data-nav="${escapeHtml(item.key)}">
            ${item.iconSvg}
            <span>${escapeHtml(item.label)}</span>
            ${badgeHtml}
          </a>
        `;
      });
      sectionsHtml += `</nav>`;
    });

    return `
      <!-- Brand Header -->
      <a class="brand" href="/candidate/dashboard" aria-label="RaviGen AI Interview Studio">
        <img class="brand-logo" src="/logo.png" alt="RaviGen AI Logo" onerror="this.onerror=null;this.src='/logo.png';">
        <div>
          <div class="brand-title"><span class="brand-name">RaviGen</span> <span class="brand-ai">AI</span></div>
          <div class="brand-sub">INTERVIEW STUDIO</div>
        </div>
      </a>

      <!-- Navigation Sections -->
      ${sectionsHtml}

      <!-- Sidebar Bottom: Upgrade Card & Profile -->
      <div class="side-foot">
        <div class="upgrade-card" id="sidebarUpgradeCard" onclick="location.href='/candidate/upgrade-pro'" role="button" tabindex="0" aria-label="Upgrade Subscription">
          <div class="upgrade-top">
            <span class="crown-icon">&#128081;</span>
            <span id="sidebarUpgradeTitle">Go Pro Plan</span>
            <span class="chevron">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
            </span>
          </div>
          <p class="upgrade-desc" id="sidebarUpgradeDesc">Unlock unlimited Gemini 2.5 Flash generations &amp; live voice mock tests.</p>
        </div>

        <div class="user-profile">
          <div class="user-avatar" id="sidebarUserAvatar">CA</div>
          <div class="user-info">
            <div class="user-name candidate-user-email" id="sidebarUserName">Candidate</div>
            <div class="user-role candidate-plan-tier" id="sidebarUserPlan">FREE TIER</div>
          </div>
          <button class="logout-btn" id="sidebarLogoutBtn" title="Sign Out / Logout" type="button" aria-label="Sign Out">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </div>
    `;
  }

  function setActiveNavigation(customPath) {
    let path = (customPath || window.location.pathname || '').toLowerCase();
    try { path = decodeURIComponent(path); } catch (_) {}
    path = path.replace(/\/+$/, '');
    if (!path) path = '/';

    const routeMap = [
      { nav: 'dashboard', paths: ['/candidate/dashboard', '/dashboard', '/candidate-dashboard.html', '/dashboard.html'] },
      { nav: 'interview-studio', paths: ['/candidate/interview-studio', '/candidate/interview-studio.html', '/interview-studio.html'] },
      { nav: 'mock-interview', paths: ['/candidate/mock-interview', '/candidate/mock-interview.html', '/mock-interview.html'] },
      { nav: 'interview-coach', paths: ['/candidate/interview-coach', '/interview-coach', '/candidate/interview-coach.html', '/interview-coach.html'] },
      { nav: 'resume-match', paths: ['/candidate/resume-match', '/candidate/resume-jd-match', '/resume-match', '/candidate/resume-match.html', '/candidate/resume-jd-match.html', '/resume-match.html'] },
      { nav: 'history', paths: ['/candidate/history', '/history', '/candidate/interview history.html', '/candidate/interview%20history.html', '/interview history.html'] },
      { nav: 'scorecard', paths: ['/scorecard', '/candidate/scorecard', '/candidate/scorecard.html', '/scorecard.html'] },
      { nav: 'company-playbooks', paths: ['/candidate/company-playbooks', '/company-playbooks', '/candidate/company-playbooks.html', '/company-playbooks.html'] }
    ];

    let matchedNav = null;
    for (const item of routeMap) {
      if (item.paths.some(p => path === p || path.startsWith(p + '/'))) {
        matchedNav = item.nav;
        break;
      }
    }

    const navLinks = document.querySelectorAll('aside.sidebar .nav-link, .sidebar .nav-link');
    navLinks.forEach(link => {
      const navKey = link.getAttribute('data-nav');
      let href = (link.getAttribute('href') || '').toLowerCase().replace(/\/+$/, '');
      try { href = decodeURIComponent(href); } catch (_) {}

      let isActive = false;
      if (matchedNav && navKey === matchedNav) {
        isActive = true;
      } else if (!matchedNav && href && (path === href || path.endsWith(href))) {
        isActive = true;
      }

      if (isActive) {
        link.classList.add('active');
        link.setAttribute('aria-current', 'page');
      } else {
        link.classList.remove('active');
        link.removeAttribute('aria-current');
      }
    });
  }

  function updateUpgradeCard(planTier) {
    const titleEl = document.getElementById('sidebarUpgradeTitle');
    const descEl = document.getElementById('sidebarUpgradeDesc');
    const cardEl = document.getElementById('sidebarUpgradeCard');
    if (!titleEl || !descEl || !cardEl) return;

    const normPlan = String(planTier || 'free').trim().toLowerCase();
    if (normPlan === 'enterprise') {
      titleEl.textContent = 'Enterprise Plan';
      descEl.textContent = 'Organization tier active with dedicated models & scorecards.';
      cardEl.setAttribute('aria-label', 'Enterprise Plan Active');
    } else if (normPlan === 'pro') {
      titleEl.textContent = 'Pro Member';
      descEl.textContent = 'All advanced features & live voice mock tests are fully unlocked.';
      cardEl.setAttribute('aria-label', 'Pro Membership Active');
    } else {
      titleEl.textContent = 'Go Pro Plan';
      descEl.textContent = 'Unlock unlimited Gemini 2.5 Flash generations & live voice mock tests.';
      cardEl.setAttribute('aria-label', 'Upgrade to Pro');
    }
  }

  async function loadCandidateProfile() {
    try {
      const res = await fetch('/api/candidate/me', {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Cache-Control': 'no-store'
        }
      });

      if (res.ok) {
        const data = await res.json();
        const user = data.user || data;
        if (user) {
          window.__CURRENT_CANDIDATE__ = user;
          const rawName = user.full_name || user.name || (user.email ? user.email.split('@')[0] : 'Candidate');
          const displayName = String(rawName).trim() || 'Candidate';
          const planLabel = formatPlanLabel(user.plan_tier);
          const initials = getInitials(displayName);

          // Update candidate name across all matching elements
          const nameEls = document.querySelectorAll('#sidebarUserName, .candidate-user-email');
          nameEls.forEach(el => { el.textContent = displayName; });

          // Update plan tier across all matching elements
          const planEls = document.querySelectorAll('#sidebarUserPlan, .candidate-plan-tier');
          planEls.forEach(el => { el.textContent = planLabel; });

          // Update avatar with crisp initials
          const avatarEls = document.querySelectorAll('#sidebarUserAvatar, .user-avatar');
          avatarEls.forEach(el => {
            if (el.tagName === 'IMG') {
              el.style.display = 'none';
              const wrap = el.parentElement;
              if (wrap) {
                let initDiv = wrap.querySelector('.user-avatar-initials');
                if (!initDiv) {
                  initDiv = document.createElement('div');
                  initDiv.className = 'user-avatar user-avatar-initials';
                  wrap.insertBefore(initDiv, el);
                }
                initDiv.textContent = initials;
              }
            } else {
              el.textContent = initials;
            }
          });

          updateUpgradeCard(user.plan_tier);
        }
      } else if (res.status === 401) {
        console.warn("[CandidateShell] Session unauthenticated or expired.");
        const path = (window.location.pathname || '').toLowerCase();
        const isPublic = path === '/scorecard' || path.startsWith('/scorecard/') || path === '/candidate/login';
        if (!isPublic && (path.startsWith('/candidate/') || path === '/dashboard' || path === '/history')) {
          window.location.replace('/candidate/login');
        }
      }
    } catch (err) {
      console.warn("[CandidateShell] Could not load candidate profile:", err);
    }
  }

  async function handleCandidateLogout(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!confirm("Are you sure you want to log out from RaviGen AI?")) {
      return;
    }
    try {
      await fetch('/candidate/logout', {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
    } catch (err) {
      console.warn("[CandidateShell] Logout request failed:", err);
    }
    try {
      localStorage.removeItem('candidate_token');
      localStorage.removeItem('candidate_user');
      sessionStorage.clear();
    } catch (_) {}
    window.location.replace('/candidate/login');
  }

  function setupMobileDrawer() {
    let scrim = document.getElementById('scrim');
    if (!scrim) {
      scrim = document.createElement('div');
      scrim.id = 'scrim';
      scrim.className = 'scrim';
      document.body.insertBefore(scrim, document.body.firstChild);
    }

    const sidebar = document.getElementById('sidebar') || document.querySelector('aside.sidebar');
    if (!sidebar) return;

    function openDrawer() {
      sidebar.classList.add('open');
      scrim.classList.add('open');
      scrim.classList.add('show');
    }

    function closeDrawer() {
      sidebar.classList.remove('open');
      scrim.classList.remove('open');
      scrim.classList.remove('show');
    }

    function toggleDrawer(e) {
      if (e) e.stopPropagation();
      if (sidebar.classList.contains('open')) {
        closeDrawer();
      } else {
        openDrawer();
      }
    }

    // Attach to any mobile menu toggle buttons
    const menuButtons = document.querySelectorAll('#menuBtn, .mob-menu-btn, .mob-btn, .menu-btn');
    menuButtons.forEach(btn => {
      btn.onclick = toggleDrawer;
    });

    scrim.onclick = closeDrawer;

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && sidebar.classList.contains('open')) {
        closeDrawer();
      }
    });

    // Close drawer when any nav-link is clicked on mobile
    const navLinks = sidebar.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth <= 820) {
          closeDrawer();
        }
      });
    });
  }

  function init() {
    const sidebar = document.getElementById('sidebar') || document.querySelector('aside.sidebar');
    if (sidebar) {
      sidebar.innerHTML = buildSidebarHTML();
    }

    setActiveNavigation();
    setupMobileDrawer();

    const logoutBtn = document.getElementById('sidebarLogoutBtn');
    if (logoutBtn) {
      logoutBtn.onclick = handleCandidateLogout;
    }
    const allLogoutBtns = document.querySelectorAll('.logout-btn');
    allLogoutBtns.forEach(btn => {
      btn.onclick = handleCandidateLogout;
    });

    loadCandidateProfile();
  }

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export public API
  window.CandidateShell = {
    init: init,
    setActiveNavigation: setActiveNavigation,
    loadCandidateProfile: loadCandidateProfile,
    handleLogout: handleCandidateLogout,
    formatPlanLabel: formatPlanLabel,
    buildSidebarHTML: buildSidebarHTML
  };
})();

