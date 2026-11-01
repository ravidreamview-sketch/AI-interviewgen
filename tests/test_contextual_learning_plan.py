"""
tests/test_contextual_learning_plan.py
======================================
Automated Test Suite for the Contextual Personalized Learning Plan feature.
Validates:
1. Evidence-Based Skill Analysis (Matched, Partially Matched, Not Evidenced, Candidate Verified)
2. Distinct Gap Taxonomy (Skill Gaps, Experience Gaps, Career Gaps)
3. 10 Mandatory Recommendation Fields
4. Priority Tiers (Critical Skills, Skills to Improve, Optional Career Growth)
5. Candidate-Controlled Roadmap Generation (No auto-enrollment)
6. Skill Reassessment & Live Match Score Recalculation
7. API Endpoints & ResumeJDMatchResponse Integration
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db_models import UserAccount, ResumeScan
from app.database import get_db
from app.auth_deps import get_current_user
from app.learning_plan_service import (
    generate_career_improvement_plan,
    build_personalized_learning_roadmap,
    reassess_candidate_progress,
    SKILL_KNOWLEDGE_BASE
)


# Mock candidate fixture
class MockCandidateUser:
    id = 9999
    email = "candidate.learning@test.com"
    full_name = "Alex Mercer"
    role = "candidate"
    plan_tier = "pro"
    is_active = True


@pytest.fixture
def mock_candidate():
    return MockCandidateUser()


@pytest.fixture
def client_with_candidate(mock_candidate):
    app.dependency_overrides[get_current_user] = lambda: mock_candidate
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def test_knowledge_base_integrity():
    """Verify that canonical skills contain authoritative resources and clear learning objectives."""
    assert "python" in SKILL_KNOWLEDGE_BASE
    assert "fastapi" in SKILL_KNOWLEDGE_BASE
    assert "postgresql" in SKILL_KNOWLEDGE_BASE

    for skill_key, data in SKILL_KNOWLEDGE_BASE.items():
        assert "what_to_learn" in data
        assert "why_it_matters" in data
        assert "target_proficiency" in data
        assert len(data.get("learning_objectives", [])) > 0
        assert len(data.get("resources", [])) > 0
        # Check that resources have canonical URLs
        for res in data["resources"]:
            assert res["url"].startswith("http")
            assert "type" in res


def test_evidence_based_classification_and_gap_separation():
    """Validates classification into matched, partial, missing evidence, and gap taxonomies."""
    sample_scan_data = {
        "scan_id": "test_scan_001",
        "target_role": "Senior Backend Engineer",
        "overall_match_score": 62.0,
        "sub_scores": {
            "required_skills": 58.0,
            "experience": 65.0,
            "domain": 55.0,
            "responsibilities": 60.0,
            "preferred_skills": 70.0
        },
        "skill_matrix": [
            {"skill": "Python", "importance": "HIGH", "match_score": 85.0, "gap_status": "matched", "evidence": "5 years Python experience"},
            {"skill": "FastAPI", "importance": "HIGH", "match_score": 50.0, "gap_status": "partial", "evidence": "Built hobby API"},
            {"skill": "PostgreSQL", "importance": "HIGH", "match_score": 20.0, "gap_status": "gap", "evidence": ""},
            {"skill": "Docker", "importance": "MEDIUM", "match_score": 10.0, "gap_status": "gap", "evidence": ""},
            {"skill": "Kubernetes", "importance": "LOW", "match_score": 0.0, "gap_status": "gap", "evidence": ""}
        ],
        "strengths": ["Python"],
        "skill_gaps": ["PostgreSQL", "Docker", "Kubernetes"],
        "critical_gaps": ["PostgreSQL"],
        "normalized_jd": {
            "job_title": "Senior Backend Engineer",
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "preferred_skills": ["Docker", "Kubernetes"],
            "experience_required": "5+ years backend systems"
        },
        "normalized_resume": {
            "candidate_name": "Alex Mercer",
            "skills": ["Python", "FastAPI", "Git"],
            "total_experience_years": 3.0
        }
    }

    plan = generate_career_improvement_plan(sample_scan_data)

    assert plan["success"] is True
    assert plan["target_role"] == "Senior Backend Engineer"
    assert "Python" in plan["matched_skills"]
    assert "FastAPI" in plan["skills_requiring_improvement"]
    assert "PostgreSQL" in plan["missing_evidence_skills"]

    # Check distinct taxonomy separation
    assert len(plan["skill_gaps"]) >= 1
    assert len(plan["experience_gaps"]) >= 1
    assert len(plan["career_gaps"]) >= 1

    # Check priority counts
    assert plan["critical_count"] >= 1
    assert plan["improvement_count"] >= 1


def test_10_mandatory_recommendation_fields():
    """Verify that every generated skill recommendation includes all 10 mandatory fields."""
    sample_scan_data = {
        "scan_id": "test_scan_002",
        "target_role": "Staff Platform Engineer",
        "overall_match_score": 55.0,
        "sub_scores": {"required_skills": 50.0},
        "skill_matrix": [
            {"skill": "FastAPI", "importance": "HIGH", "match_score": 45.0, "gap_status": "partial"},
            {"skill": "Redis", "importance": "HIGH", "match_score": 0.0, "gap_status": "gap"}
        ],
        "critical_gaps": ["Redis"],
        "skill_gaps": ["FastAPI", "Redis"],
        "normalized_jd": {"job_title": "Staff Platform Engineer"},
        "normalized_resume": {"candidate_name": "Test Candidate"}
    }

    plan = generate_career_improvement_plan(sample_scan_data)
    recs = plan["recommendations"]
    assert len(recs) >= 2

    mandatory_fields = [
        "what_to_learn",               # 1. What to learn
        "why_it_matters",              # 2. Why it matters for JD
        "related_jd_requirement",      # 3. Related JD requirement
        "current_proficiency",         # 4. Current proficiency
        "target_proficiency",          # 5. Target proficiency
        "learning_objectives",         # 6. Learning objectives
        "resources",                   # 7. Recommended resources
        "practical_exercises",         # 8. Practical exercises
        "suggested_project",           # 9. Suggested project
        "completion_criteria",         # 10. Completion criteria
        "estimated_effort"             # 10b. Estimated effort
    ]

    for rec in recs:
        for field in mandatory_fields:
            assert field in rec, f"Missing mandatory field '{field}' in recommendation for {rec.get('skill')}"
            assert rec[field], f"Field '{field}' must not be empty for {rec.get('skill')}"


def test_priority_tier_assignment():
    """Verify tier assignment: Critical (P1), Improvement (P2), Career Growth (P3)."""
    sample_scan_data = {
        "scan_id": "test_scan_003",
        "target_role": "Lead Architect",
        "overall_match_score": 60.0,
        "sub_scores": {},
        "skill_matrix": [
            {"skill": "PostgreSQL", "importance": "HIGH", "match_score": 0.0, "gap_status": "gap"},
            {"skill": "FastAPI", "importance": "HIGH", "match_score": 55.0, "gap_status": "partial"},
            {"skill": "Kubernetes", "importance": "LOW", "match_score": 0.0, "gap_status": "gap"}
        ],
        "critical_gaps": ["PostgreSQL"],
        "skill_gaps": ["PostgreSQL", "Kubernetes"],
        "normalized_jd": {},
        "normalized_resume": {}
    }

    plan = generate_career_improvement_plan(sample_scan_data)
    recs = plan["recommendations"]

    rec_map = {r["skill"].lower(): r for r in recs}
    assert rec_map["postgresql"]["priority"] == "CRITICAL"
    assert rec_map["fastapi"]["priority"] == "IMPROVEMENT"


def test_build_personalized_roadmap():
    """Verify building candidate-approved modular roadmap with phases, milestones, capstone, and score boost."""
    selected_skills = ["FastAPI", "PostgreSQL", "Docker"]
    roadmap = build_personalized_learning_roadmap(
        selected_skill_names=selected_skills,
        target_role="Full Stack Engineer",
        overall_match_score=65.0
    )

    assert roadmap["success"] is True
    assert roadmap["target_role"] == "Full Stack Engineer"
    assert roadmap["total_skills"] == 3
    assert len(roadmap["phases"]) == 3
    assert roadmap["projected_match_score"] > roadmap["current_match_score"]
    assert "capstone_project" in roadmap
    assert len(roadmap["capstone_project"]["deliverables"]) > 0
    assert len(roadmap["assessment_rubric"]) > 0


def test_skill_reassessment_calculation():
    """Verify step 9 skill reassessment score boost and skill matrix status update."""
    original_score = 65.0
    initial_matrix = [
        {"skill": "FastAPI", "importance": "HIGH", "gap_status": "gap"},
        {"skill": "PostgreSQL", "importance": "HIGH", "gap_status": "gap"},
        {"skill": "Python", "importance": "HIGH", "gap_status": "matched"}
    ]

    reassessment = reassess_candidate_progress(
        target_role="Backend Developer",
        original_match_score=original_score,
        skill_matrix=initial_matrix,
        completed_skills=["FastAPI"],
        candidate_verified_skills=["PostgreSQL"]
    )

    assert reassessment["success"] is True
    assert reassessment["recalculated_match_score"] > original_score
    assert reassessment["gaps_closed_count"] == 1
    assert reassessment["skills_verified_count"] == 1

    # Check updated matrix items
    updated_map = {item["skill"].lower(): item for item in reassessment["updated_skill_matrix"]}
    assert updated_map["fastapi"]["gap_status"] == "acquired"
    assert "Acquired" in updated_map["fastapi"]["status_label"]
    assert updated_map["postgresql"]["gap_status"] == "verified"
    assert "Verified" in updated_map["postgresql"]["status_label"]
    assert updated_map["python"]["gap_status"] == "matched"


def test_learning_plan_api_routes(client_with_candidate):
    """Verify HTTP endpoints /api/candidate/learning-plan/generate, /build, and /reassess."""
    # 1. Generate endpoint
    gen_resp = client_with_candidate.post(
        "/api/candidate/learning-plan/generate",
        json={"target_role": "Backend Specialist"}
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["success"] is True
    assert "recommendations" in gen_data

    # 2. Build roadmap endpoint
    build_resp = client_with_candidate.post(
        "/api/candidate/learning-plan/build",
        json={
            "target_role": "Backend Specialist",
            "selected_skills": ["Python", "FastAPI"],
            "candidate_verified_skills": []
        }
    )
    assert build_resp.status_code == 200
    build_data = build_resp.json()
    assert build_data["success"] is True
    assert "phases" in build_data
    assert build_data["projected_match_score"] > 65.0

    # 3. Reassess endpoint
    reassess_resp = client_with_candidate.post(
        "/api/candidate/learning-plan/reassess",
        json={
            "target_role": "Backend Specialist",
            "completed_skills": ["Python"],
            "candidate_verified_skills": ["FastAPI"]
        }
    )
    assert reassess_resp.status_code == 200
    reassess_data = reassess_resp.json()
    assert reassess_data["success"] is True
    assert reassess_data["recalculated_match_score"] > 65.0



def test_supervisor_menu_management_integration():
    """
    Verify Supervisor Menu Management Integration:
    1. Default menu definition exists for 'Personalized Learning Plan' with order 9 and status 'active'.
    2. Supervisor can view, toggle to 'disabled', and toggle back to 'active'.
    3. When disabled, public menus and backend candidate APIs are blocked with 403 Forbidden.
    4. When active, public menus and backend candidate APIs succeed.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base
    from app.db_models import UserAccount
    from app.security import hash_password
    from app.admin_routes import DEFAULT_NAVIGATION_MENUS

    # 1. Verify DEFAULT_NAVIGATION_MENUS entry
    menu_entry = next((m for m in DEFAULT_NAVIGATION_MENUS if m["id"] == "menu-learning-plan"), None)
    assert menu_entry is not None, "menu-learning-plan must exist in DEFAULT_NAVIGATION_MENUS"
    assert menu_entry["name"] == "Personalized Learning Plan"
    assert menu_entry["route"] == "learning-plan"
    assert menu_entry["order"] == 9
    assert menu_entry["status"] == "active"
    assert "candidate" in menu_entry["allowed_roles"]

    # 2. Setup isolated in-memory test database
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    db = TestingSessionLocal()
    admin_user = UserAccount(
        email="supervisor@test.com",
        password_hash=hash_password("SupervisorPass123!"),
        role="super_admin",
        plan_tier="enterprise",
        is_active=True
    )
    cand_user = UserAccount(
        email="cand.menu.test@test.com",
        password_hash=hash_password("CandidatePass123!"),
        role="candidate",
        plan_tier="pro",
        is_active=True
    )
    db.add(admin_user)
    db.add(cand_user)
    db.commit()
    db.refresh(admin_user)
    db.refresh(cand_user)
    db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            # Login as supervisor to get token
            login_res = client.post("/api/admin/login", json={"email": "supervisor@test.com", "password": "SupervisorPass123!"})
            assert login_res.status_code == 200
            admin_token = login_res.json()["token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}

            # Login as candidate to get token
            cand_login = client.post("/api/candidate/login", json={"email": "cand.menu.test@test.com", "password": "CandidatePass123!"})
            assert cand_login.status_code == 200
            cand_token = cand_login.cookies.get("candidate_session")
            cand_headers = {"Cookie": f"candidate_session={cand_token}"}

            # A. When Active: Menu is in /api/public/menus
            pub_res = client.get("/api/public/menus")
            assert pub_res.status_code == 200
            pub_menus = [m["name"] for m in pub_res.json()["menus"]]
            assert "Personalized Learning Plan" in pub_menus

            # Candidate can generate learning plan
            gen_res = client.post("/api/candidate/learning-plan/generate", headers=cand_headers, json={"target_role": "Backend Engineer"})
            assert gen_res.status_code == 200

            # Candidate can build roadmap
            build_res = client.post("/api/candidate/learning-plan/build", headers=cand_headers, json={"target_role": "Backend Engineer", "selected_skills": ["Python"]})
            assert build_res.status_code == 200

            # Candidate can reassess
            reassess_res = client.post("/api/candidate/learning-plan/reassess", headers=cand_headers, json={"target_role": "Backend Engineer", "completed_skills": ["Python"], "candidate_verified_skills": []})
            assert reassess_res.status_code == 200

            # Direct route returns 200
            direct_res = client.get("/candidate/learning-plan")
            assert direct_res.status_code == 200

            # B. Supervisor Disables the feature
            disable_res = client.patch(
                "/api/admin/menus/menu-learning-plan",
                headers=admin_headers,
                json={"status": "disabled"}
            )
            assert disable_res.status_code == 200
            assert "hidden from candidates" in disable_res.json()["message"]

            # C. When Disabled: Public menus exclude it
            pub_res2 = client.get("/api/public/menus")
            assert pub_res2.status_code == 200
            pub_menus2 = [m["name"] for m in pub_res2.json()["menus"]]
            assert "Personalized Learning Plan" not in pub_menus2

            # Direct candidate route is blocked with 403 Forbidden
            blocked_page = client.get("/candidate/learning-plan")
            assert blocked_page.status_code == 403
            assert "Feature Temporarily Disabled" in blocked_page.text
            assert "Personalized Learning Plan" in blocked_page.text

            # Backend Candidate API endpoints are blocked with 403 Forbidden
            gen_blocked = client.post("/api/candidate/learning-plan/generate", headers=cand_headers, json={"target_role": "Backend Engineer"})
            assert gen_blocked.status_code == 403
            assert "Personalized Learning Plan is currently disabled by administrator." in gen_blocked.json()["detail"]

            build_blocked = client.post("/api/candidate/learning-plan/build", headers=cand_headers, json={"target_role": "Backend Engineer", "selected_skills": ["Python"]})
            assert build_blocked.status_code == 403
            assert "Personalized Learning Plan is currently disabled by administrator." in build_blocked.json()["detail"]

            reassess_blocked = client.post("/api/candidate/learning-plan/reassess", headers=cand_headers, json={"target_role": "Backend Engineer", "completed_skills": ["Python"], "candidate_verified_skills": []})
            assert reassess_blocked.status_code == 403
            assert "Personalized Learning Plan is currently disabled by administrator." in reassess_blocked.json()["detail"]

            # D. Supervisor Re-enables the feature
            enable_res = client.patch(
                "/api/admin/menus/menu-learning-plan",
                headers=admin_headers,
                json={"status": "active"}
            )
            assert enable_res.status_code == 200
            assert "now visible to candidates" in enable_res.json()["message"]

            # Public menus include it again
            pub_res3 = client.get("/api/public/menus")
            assert "Personalized Learning Plan" in [m["name"] for m in pub_res3.json()["menus"]]

            # Candidate endpoints function normally again
            gen_ok = client.post("/api/candidate/learning-plan/generate", headers=cand_headers, json={"target_role": "Backend Engineer"})
            assert gen_ok.status_code == 200

    finally:
        app.dependency_overrides.pop(get_db, None)
