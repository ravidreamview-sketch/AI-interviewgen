import os
import sys
import json
import io
import zipfile
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from sqlalchemy import text
from app.database import get_db, SessionLocal, Base, engine
from app.db_models import UserAccount, ResumeScan, RebuiltResume, AuditLog
from app.security import hash_password, create_access_token
from app.resume_rebuilder_service import (
    rebuild_resume_content,
    export_as_docx,
    export_as_html_printable,
    export_as_markdown,
    export_as_txt,
    generate_rebuild_id
)

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_test_users():
    """Sets up two test candidate users for IDOR and isolation testing."""
    db = SessionLocal()
    
    # Candidate A
    cand_a = db.query(UserAccount).filter(UserAccount.email == "rebuild_cand_a@test.com").first()
    if not cand_a:
        cand_a = UserAccount(
            email="rebuild_cand_a@test.com",
            full_name="Alice Candidate",
            password_hash=hash_password("Password123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(cand_a)
        db.commit()
        db.refresh(cand_a)
        
    # Candidate B (Attacker / Different Tenant)
    cand_b = db.query(UserAccount).filter(UserAccount.email == "rebuild_cand_b@test.com").first()
    if not cand_b:
        cand_b = UserAccount(
            email="rebuild_cand_b@test.com",
            full_name="Bob Candidate",
            password_hash=hash_password("Password123!"),
            role="candidate",
            plan_tier="free",
            is_active=True
        )
        db.add(cand_b)
        db.commit()
        db.refresh(cand_b)

    # Seed sample ResumeScan for Candidate A
    scan_a = db.query(ResumeScan).filter(ResumeScan.scan_id == "scan_test_rebuilder_a").first()
    if not scan_a:
        scan_a = ResumeScan(
            scan_id="scan_test_rebuilder_a",
            user_id=cand_a.id,
            target_role="Senior Cloud Engineer",
            match_score=52.5,
            overall_match_score=52.5,
            normalized_resume="Alice Candidate\nalice@test.com\nExperience at Tech Corp building Python and AWS services.",
            skill_matrix=json.dumps([
                {"skill_name": "Python", "status": "Acquired", "importance": "HIGH"},
                {"skill_name": "Kubernetes", "status": "Missing", "importance": "HIGH"},
                {"skill_name": "Terraform", "status": "Missing", "importance": "MEDIUM"}
            ]),
            critical_gaps=json.dumps(["Kubernetes", "Terraform"]),
            created_at=datetime.now(timezone.utc)
        )
        db.add(scan_a)
        db.commit()

    cand_a_id = cand_a.id
    cand_b_id = cand_b.id
    db.close()

    token_a = create_access_token({"sub": str(cand_a_id), "role": "candidate", "email": "rebuild_cand_a@test.com"})
    token_b = create_access_token({"sub": str(cand_b_id), "role": "candidate", "email": "rebuild_cand_b@test.com"})

    return {
        "cand_a_id": cand_a_id,
        "cand_b_id": cand_b_id,
        "token_a": token_a,
        "token_b": token_b,
        "scan_a_id": "scan_test_rebuilder_a"
    }


def test_resume_rebuilder_unit_synthesis():
    """Validates pure-function synthesis, score calculation, and improvements summary."""
    resume_text = "John Doe\njohn@example.com\nSoftware developer with Python experience."
    res = rebuild_resume_content(
        original_resume_text=resume_text,
        target_role="Lead Backend Architect",
        critical_gaps=["Distributed Systems", "Kafka", "Docker"],
        baseline_ats_score=48.0
    )
    assert res["rebuilt_resume_text"] is not None
    assert "John Doe" in res["rebuilt_resume_text"]
    assert "Lead Backend Architect" in res["rebuilt_resume_text"]
    assert res["ats_projected_score"] >= 80.0
    assert len(res["improvements_summary"]) >= 3
    assert "Distributed Systems" in res["tailored_skills"] or "Kafka" in res["tailored_skills"]


def test_api_generate_rebuilt_resume(setup_test_users):
    """Tests POST /api/candidate/resume-rebuild/generate."""
    data = setup_test_users
    headers = {"Authorization": f"Bearer {data['token_a']}"}

    payload = {
        "scan_id": data["scan_a_id"],
        "target_role": "Senior Cloud Engineer",
        "focus_areas": ["Kubernetes", "AWS"]
    }

    res = client.post("/api/candidate/resume-rebuild/generate", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["rebuild_id"].startswith("rebuild_")
    assert body["version_number"] >= 1
    assert body["target_role"] == "Senior Cloud Engineer"
    assert body["ats_projected_score"] > 80.0
    assert "Alice Candidate" in body["rebuilt_resume_text"]

    # Verify original resume was NOT modified
    db = SessionLocal()
    scan = db.query(ResumeScan).filter(ResumeScan.scan_id == data["scan_a_id"]).first()
    assert scan is not None
    assert scan.match_score == 52.5
    assert "Alice Candidate" in scan.normalized_resume
    db.close()


def test_api_rebuild_version_progression(setup_test_users):
    """Tests version incrementation on subsequent rebuilds."""
    data = setup_test_users
    headers = {"Authorization": f"Bearer {data['token_a']}"}

    # Generate version 2
    res2 = client.post("/api/candidate/resume-rebuild/generate", json={
        "scan_id": data["scan_a_id"],
        "target_role": "Staff Platform Engineer"
    }, headers=headers)
    assert res2.status_code == 200
    v2_body = res2.json()
    assert v2_body["version_number"] >= 2

    # Query versions list
    list_res = client.get("/api/candidate/resume-rebuild/versions", headers=headers)
    assert list_res.status_code == 200
    versions = list_res.json()["versions"]
    assert len(versions) >= 2
    assert versions[0]["version_number"] > versions[1]["version_number"]


def test_api_get_and_update_rebuilt_draft(setup_test_users):
    """Tests GET and PUT /api/candidate/resume-rebuild/{rebuild_id}."""
    data = setup_test_users
    headers = {"Authorization": f"Bearer {data['token_a']}"}

    # Generate a draft to test
    gen_res = client.post("/api/candidate/resume-rebuild/generate", json={
        "scan_id": data["scan_a_id"],
        "target_role": "Senior Cloud Engineer"
    }, headers=headers)
    rebuild_id = gen_res.json()["rebuild_id"]

    # GET version details
    get_res = client.get(f"/api/candidate/resume-rebuild/{rebuild_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["rebuild_id"] == rebuild_id

    # PUT update draft text
    updated_text = "# Alice Candidate\n**Senior Cloud Architect**\nUpdated custom content with verified achievements."
    put_res = client.put(f"/api/candidate/resume-rebuild/{rebuild_id}", json={
        "rebuilt_resume_text": updated_text,
        "target_role": "Senior Cloud Architect"
    }, headers=headers)
    assert put_res.status_code == 200
    put_body = put_res.json()
    assert put_body["target_role"] == "Senior Cloud Architect"
    assert "Updated custom content" in put_body["rebuilt_resume_text"]


def test_api_strict_idor_isolation(setup_test_users):
    """
    CRITICAL: Validates that Candidate B CANNOT access, edit, or export Candidate A's rebuilt resume.
    """
    data = setup_test_users
    headers_a = {"Authorization": f"Bearer {data['token_a']}"}
    headers_b = {"Authorization": f"Bearer {data['token_b']}"}

    # Candidate A creates a rebuilt resume
    gen_res = client.post("/api/candidate/resume-rebuild/generate", json={
        "scan_id": data["scan_a_id"],
        "target_role": "Lead Architect"
    }, headers=headers_a)
    rebuild_id = gen_res.json()["rebuild_id"]

    # Candidate B tries to GET Candidate A's rebuild -> Must return 404
    get_attack = client.get(f"/api/candidate/resume-rebuild/{rebuild_id}", headers=headers_b)
    assert get_attack.status_code == 404

    # Candidate B tries to PUT Candidate A's rebuild -> Must return 404
    put_attack = client.put(f"/api/candidate/resume-rebuild/{rebuild_id}", json={
        "rebuilt_resume_text": "Maliciously overwritten resume text"
    }, headers=headers_b)
    assert put_attack.status_code == 404

    # Candidate B tries to EXPORT Candidate A's rebuild -> Must return 404
    export_attack = client.post(f"/api/candidate/resume-rebuild/{rebuild_id}/export", json={
        "format": "docx"
    }, headers=headers_b)
    assert export_attack.status_code == 404


def test_api_multi_format_export(setup_test_users):
    """Validates DOCX, Markdown, TXT, and PDF/HTML exports."""
    data = setup_test_users
    headers = {"Authorization": f"Bearer {data['token_a']}"}

    # Generate a draft
    gen_res = client.post("/api/candidate/resume-rebuild/generate", json={
        "scan_id": data["scan_a_id"],
        "target_role": "Senior Cloud Engineer"
    }, headers=headers)
    rebuild_id = gen_res.json()["rebuild_id"]

    # 1. Export DOCX
    docx_res = client.post(f"/api/candidate/resume-rebuild/{rebuild_id}/export", json={"format": "docx"}, headers=headers)
    assert docx_res.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in docx_res.headers.get("content-type", "")
    assert len(docx_res.content) > 500
    # Verify DOCX is a valid ZIP package
    with zipfile.ZipFile(io.BytesIO(docx_res.content)) as zf:
        assert "word/document.xml" in zf.namelist()

    # 2. Export Markdown
    md_res = client.post(f"/api/candidate/resume-rebuild/{rebuild_id}/export", json={"format": "markdown"}, headers=headers)
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers.get("content-type", "")
    assert len(md_res.content) > 100

    # 3. Export TXT
    txt_res = client.post(f"/api/candidate/resume-rebuild/{rebuild_id}/export", json={"format": "txt"}, headers=headers)
    assert txt_res.status_code == 200
    assert "text/plain" in txt_res.headers.get("content-type", "")

    # 4. Export PDF / HTML
    pdf_res = client.post(f"/api/candidate/resume-rebuild/{rebuild_id}/export", json={"format": "pdf"}, headers=headers)
    assert pdf_res.status_code == 200
    assert "text/html" in pdf_res.headers.get("content-type", "")
    assert "@media print" in pdf_res.text


def test_audit_logging_compliance(setup_test_users):
    """Verifies that rebuild actions generate persistent entries in audit_logs."""
    data = setup_test_users
    headers = {"Authorization": f"Bearer {data['token_a']}"}

    client.post("/api/candidate/resume-rebuild/generate", json={
        "scan_id": data["scan_a_id"],
        "target_role": "Audited Role"
    }, headers=headers)

    db = SessionLocal()
    recent_audit = db.query(AuditLog).filter(
        AuditLog.user_id == data["cand_a_id"],
        AuditLog.action == "RESUME_REBUILD_GENERATED"
    ).order_by(AuditLog.id.desc()).first()
    assert recent_audit is not None
    assert recent_audit.resource.startswith("rebuild_")
    db.close()


def test_factual_integrity_no_hallucinated_metrics():
    """Verifies that the synthesis engine never invents fabricated percentages or statistics."""
    source_resume = "Jane Candidate\njane@test.com\nSoftware engineer writing Python microservices and backend databases."
    res = rebuild_resume_content(
        original_resume_text=source_resume,
        target_role="Lead Software Engineer"
    )
    rebuilt_text = res["rebuilt_resume_text"]
    
    # Assert no invented statistics
    assert "38%" not in rebuilt_text
    assert "25,000+" not in rebuilt_text
    assert "45%" not in rebuilt_text
    assert "60%" not in rebuilt_text
    
    # Assert missing metrics are cleanly flagged with candidate confirmation placeholders
    assert "[insert metric:" in rebuilt_text


def test_factual_integrity_no_invented_employers_or_certifications():
    """Verifies that fictional companies and unearned certifications are never fabricated."""
    source_resume = "Developer Candidate\ndev@test.com\nExperience with Python and Docker."
    res = rebuild_resume_content(
        original_resume_text=source_resume,
        target_role="Full Stack Engineer"
    )
    rebuilt_text = res["rebuilt_resume_text"]
    
    # Assert fictional employers are never present
    assert "Horizon Tech Solutions" not in rebuilt_text
    assert "Nexus Cloud Systems" not in rebuilt_text
    
    # Assert unearned certifications are never present
    assert "AWS Certified Solutions Architect" not in rebuilt_text
    assert "AWS Certified" not in rebuilt_text


def test_factual_integrity_preserves_provided_data():
    """Verifies that candidate-provided companies, metrics, and degrees are accurately preserved."""
    source_resume = """Alex Morgan
alex.morgan@example.com | (555) 234-5678
Software Engineer at Acme Corp developing scalable distributed cloud services.
Optimized distributed cache queries reducing p99 latency by 42%.
B.S. in Computer Science — State University"""

    res = rebuild_resume_content(
        original_resume_text=source_resume,
        target_role="Staff Systems Engineer"
    )
    rebuilt_text = res["rebuilt_resume_text"]
    
    assert "Alex Morgan" in rebuilt_text
    assert "Acme Corp" in rebuilt_text
    assert "42%" in rebuilt_text
    assert "B.S. in Computer Science" in rebuilt_text


def test_candidate_account_deletion_cascades_safely():
    """Tests referential integrity: deleting a candidate account cascades safely to rebuilt resumes."""
    db = SessionLocal()
    if engine.dialect.name == "sqlite":
        db.execute(text("PRAGMA foreign_keys = ON;"))
    import uuid
    u_suffix = uuid.uuid4().hex[:8]
    
    # Create isolated test user
    del_user = UserAccount(
        email=f"cascade_user_{u_suffix}@example.com",
        full_name="Cascade Test User",
        password_hash=hash_password("Password123!"),
        role="candidate",
        plan_tier="free",
        is_active=True
    )
    db.add(del_user)
    db.commit()
    db.refresh(del_user)
    
    uid = del_user.id
    
    # Add dependent resume scan
    scan = ResumeScan(
        scan_id=f"scan_cascade_{u_suffix}",
        user_id=uid,
        target_role="Test Role",
        match_score=60.0
    )
    db.add(scan)
    
    # Add dependent rebuilt resume
    rebuilt = RebuiltResume(
        rebuild_id=f"rebuild_cascade_{u_suffix}",
        user_id=uid,
        scan_id=f"scan_cascade_{u_suffix}",
        version_number=1,
        target_role="Test Role",
        rebuilt_resume_text="Sample text for cascade test"
    )
    db.add(rebuilt)
    db.commit()
    
    # Verify rows exist
    assert db.query(ResumeScan).filter(ResumeScan.user_id == uid).count() == 1
    assert db.query(RebuiltResume).filter(RebuiltResume.user_id == uid).count() == 1
    
    # Delete user account: cascade removes dependent records
    db.delete(del_user)
    db.commit()
    
    # Verify cascade cleaned up dependent rows
    assert db.query(ResumeScan).filter(ResumeScan.user_id == uid).count() == 0
    assert db.query(RebuiltResume).filter(RebuiltResume.user_id == uid).count() == 0
    db.close()
