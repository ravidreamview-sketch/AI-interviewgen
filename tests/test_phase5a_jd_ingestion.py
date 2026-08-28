"""
Phase 5A Test Suite: Job Description (JD) Ingestion & Multi-Layered SSRF Defense
Tests all 22 required scenarios:
1. Valid public URL
2. HTTPS URL
3. HTTP URL
4. Malformed URL
5. Localhost rejection
6. 127.0.0.1 rejection
7. Private IP rejection
8. Metadata endpoint rejection
9. Redirect to private IP
10. Maximum redirect count
11. Timeout handling
12. Oversized response (>1.5 MB)
13. Unsupported content type
14. Valid HTML extraction
15. Valid plain text extraction
16. Authentication required (401)
17. Tenant isolation (authenticated user)
18. PDF extraction
19. DOCX extraction
20. TXT extraction
21. Incomplete JD (no fabricated data)
22. Bot-blocked page fallback (Cloudflare / CAPTCHA)
"""

import os
import sys
import io
import zipfile
import socket
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount
from app.security import hash_password, create_access_token
from app.auth_deps import FAILED_LOGIN_ATTEMPTS
from app.jd_service import (
    validate_and_resolve_url,
    safe_fetch_job_url,
    extract_text_from_html,
    extract_text_from_txt,
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_document,
    normalize_job_description,
    SSRFValidationError,
)
from app.models import NormalizedJobDescription

# Setup isolated test in-memory SQLite database with StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


class TestPhase5AJobDescriptionIngestion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed test candidate
        candidate = UserAccount(
            email="candidate_phase5@example.com",
            password_hash=hash_password("SecurePassword123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        self.candidate_id = candidate.id
        self.candidate_email = candidate.email
        db.close()

        token = create_access_token({"sub": self.candidate_id, "email": self.candidate_email, "role": "candidate"})
        self.auth_headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)

    # --------------------------------------------------------------------------
    # 1. Valid Public URL Extraction
    # --------------------------------------------------------------------------
    def test_01_valid_public_url(self):
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Job Details</title></head>
        <body>
            <h1>Job Title: Senior Backend Engineer</h1>
            <h2>Company: CloudTech Solutions</h2>
            <p>Location: San Francisco, CA (Remote)</p>
            <p>Experience: 5+ years of experience</p>
            <p>Type: Full-time</p>
            <section>
                <h3>Responsibilities:</h3>
                <ul>
                    <li>Architect and build scalable distributed microservices in Python.</li>
                    <li>Design resilient asynchronous event-driven architectures with Kafka.</li>
                    <li>Collaborate with cross-functional product and DevOps teams.</li>
                </ul>
            </section>
            <section>
                <h3>Requirements:</h3>
                <p>Strong experience with Python, FastAPI, PostgreSQL, Docker, Kubernetes, and AWS.</p>
            </section>
            <section>
                <h3>Preferred:</h3>
                <p>Experience with Redis, GraphQL, and Prometheus is a plus.</p>
            </section>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.encoding = "utf-8"
        mock_response.iter_content.return_value = [sample_html.encode("utf-8")]

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_response):
                success, status, text, final_url = safe_fetch_job_url("https://jobs.example.com/roles/123")
                self.assertTrue(success)
                self.assertEqual(status, "extracted")
                self.assertIn("Senior Backend Engineer", text)

                normalized = normalize_job_description(text, source_type="public_url", source_url=final_url)
                self.assertEqual(normalized.job_title, "Senior Backend Engineer")
                self.assertEqual(normalized.company, "CloudTech Solutions")
                self.assertEqual(normalized.employment_type, "Full-time")
                self.assertIn("Python", normalized.required_skills)
                self.assertIn("FastAPI", normalized.required_skills)
                self.assertIn("Docker", normalized.tools)
                self.assertIn("Redis", normalized.preferred_skills)

    # --------------------------------------------------------------------------
    # 2. HTTPS URL
    # --------------------------------------------------------------------------
    def test_02_https_url(self):
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))]):
            clean_url, ip, port = validate_and_resolve_url("https://careers.google.com/jobs/results/123")
            self.assertTrue(clean_url.startswith("https://"))
            self.assertEqual(port, 443)
            self.assertEqual(ip, "142.250.190.46")

    # --------------------------------------------------------------------------
    # 3. HTTP URL
    # --------------------------------------------------------------------------
    def test_03_http_url(self):
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
            clean_url, ip, port = validate_and_resolve_url("http://example.com/job")
            self.assertTrue(clean_url.startswith("http://"))
            self.assertEqual(port, 80)
            self.assertEqual(ip, "93.184.216.34")

    # --------------------------------------------------------------------------
    # 4. Malformed URL Rejection
    # --------------------------------------------------------------------------
    def test_04_malformed_url(self):
        malformed_urls = [
            "not-a-valid-url",
            "ftp://ftp.example.com/job.txt",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "",
            "http://",
            "https://",
        ]
        for bad_url in malformed_urls:
            success, status, msg, _ = safe_fetch_job_url(bad_url)
            self.assertFalse(success)
            self.assertEqual(status, "invalid_url")

    # --------------------------------------------------------------------------
    # 5. Localhost Rejection
    # --------------------------------------------------------------------------
    def test_05_localhost_rejection(self):
        localhost_urls = [
            "http://localhost/job",
            "http://localhost:8000/api",
            "https://localhost/careers",
            "http://localhost.localdomain/job",
        ]
        for url in localhost_urls:
            success, status, msg, _ = safe_fetch_job_url(url)
            self.assertFalse(success)
            self.assertEqual(status, "ssrf_blocked")
            self.assertIn("forbidden", msg.lower())

    # --------------------------------------------------------------------------
    # 6. 127.0.0.1 Rejection
    # --------------------------------------------------------------------------
    def test_06_127_0_0_1_rejection(self):
        loopback_urls = [
            "http://127.0.0.1/jobs",
            "http://127.0.0.1:8080/admin",
            "http://127.0.1.1/secret",
            "http://[::1]/internal",
        ]
        for url in loopback_urls:
            success, status, msg, _ = safe_fetch_job_url(url)
            self.assertFalse(success)
            self.assertEqual(status, "ssrf_blocked")

    # --------------------------------------------------------------------------
    # 7. Private IP Rejection (RFC 1918, RFC 4193, CGNAT)
    # --------------------------------------------------------------------------
    def test_07_private_ip_rejection(self):
        private_urls = [
            "http://10.0.0.1/jobs",
            "http://10.255.0.1/api",
            "http://172.16.0.5/job",
            "http://172.31.255.255/roles",
            "http://192.168.1.1/careers",
            "http://100.64.0.1/cgnat-job",
            "http://[fe80::1]/link-local",
            "http://[fc00::1]/unique-local",
        ]
        for url in private_urls:
            success, status, msg, _ = safe_fetch_job_url(url)
            self.assertFalse(success)
            self.assertEqual(status, "ssrf_blocked")

    # --------------------------------------------------------------------------
    # 8. Metadata Endpoint Rejection (AWS / GCP / Azure)
    # --------------------------------------------------------------------------
    def test_08_metadata_endpoint_rejection(self):
        metadata_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.170.2/v2/credentials",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata.google/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
            "http://0.0.0.0/internal",
        ]
        for url in metadata_urls:
            success, status, msg, _ = safe_fetch_job_url(url)
            self.assertFalse(success)
            self.assertEqual(status, "ssrf_blocked")

    # --------------------------------------------------------------------------
    # 9. Redirect to Private IP (Hop Validation)
    # --------------------------------------------------------------------------
    def test_09_redirect_to_private_ip(self):
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.headers = {"Location": "http://192.168.1.1/secret-job"}

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_redirect):
                success, status, msg, _ = safe_fetch_job_url("https://public-site.com/redirect-to-private")
                self.assertFalse(success)
                self.assertEqual(status, "ssrf_blocked")
                self.assertIn("forbidden", msg.lower())

    # --------------------------------------------------------------------------
    # 10. Maximum Redirect Count (>3 Hops)
    # --------------------------------------------------------------------------
    def test_10_maximum_redirect_count(self):
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.headers = {"Location": "https://public-site.com/hop"}

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_redirect):
                success, status, msg, _ = safe_fetch_job_url("https://public-site.com/hop0")
                self.assertFalse(success)
                self.assertEqual(status, "fallback_required")
                self.assertIn("redirect limit", msg.lower())

    # --------------------------------------------------------------------------
    # 11. Timeout Handling
    # --------------------------------------------------------------------------
    def test_11_timeout_handling(self):
        import requests.exceptions
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", side_effect=requests.exceptions.Timeout("Connection timed out")):
                success, status, msg, _ = safe_fetch_job_url("https://slow-server.com/job")
                self.assertFalse(success)
                self.assertEqual(status, "fallback_required")
                self.assertIn("timed out", msg.lower())

    # --------------------------------------------------------------------------
    # 12. Oversized Response (>1.5 MB)
    # --------------------------------------------------------------------------
    def test_12_oversized_response(self):
        # 1. Test Content-Length header guard
        mock_response_header = MagicMock()
        mock_response_header.status_code = 200
        mock_response_header.headers = {
            "Content-Type": "text/html",
            "Content-Length": "2000000"  # 2MB
        }
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_response_header):
                success, status, msg, _ = safe_fetch_job_url("https://example.com/oversized-header")
                self.assertFalse(success)
                self.assertEqual(status, "fallback_required")
                self.assertIn("1.5 mb", msg.lower())

        # 2. Test chunk streaming limit
        mock_response_stream = MagicMock()
        mock_response_stream.status_code = 200
        mock_response_stream.headers = {"Content-Type": "text/html"}
        mock_response_stream.iter_content.return_value = [b"A" * 65536 for _ in range(30)]  # ~1.96 MB
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_response_stream):
                success, status, msg, _ = safe_fetch_job_url("https://example.com/oversized-stream")
                self.assertFalse(success)
                self.assertEqual(status, "fallback_required")
                self.assertIn("1.5 mb", msg.lower())

    # --------------------------------------------------------------------------
    # 13. Unsupported Content-Type
    # --------------------------------------------------------------------------
    def test_13_unsupported_content_type(self):
        unsupported_types = [
            "application/octet-stream",
            "image/png",
            "application/zip",
            "video/mp4",
            "audio/mpeg",
        ]
        for ctype in unsupported_types:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.headers = {"Content-Type": ctype}
            mock_res.iter_content.return_value = [b"binary data"]

            with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
                with patch("requests.Session.get", return_value=mock_res):
                    success, status, msg, _ = safe_fetch_job_url("https://example.com/download.bin")
                    self.assertFalse(success)
                    self.assertEqual(status, "unsupported_content_type")
                    self.assertIn("unsupported content type", msg.lower())

    # --------------------------------------------------------------------------
    # 14. Valid HTML Extraction
    # --------------------------------------------------------------------------
    def test_14_valid_html_extraction(self):
        html_doc = """
        <html>
        <head><script>var tracker = 123;</script><style>body { color: red; }</style></head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <article>
                <h1>Position: Full Stack Engineer</h1>
                <p>We are looking for an experienced full stack developer.</p>
                <ul>
                    <li>Build REST APIs with Node.js and TypeScript.</li>
                    <li>Create responsive UIs using React.</li>
                </ul>
            </article>
            <footer><p>&copy; 2026 Tech Inc.</p></footer>
        </body>
        </html>
        """
        extracted = extract_text_from_html(html_doc)
        self.assertNotIn("var tracker", extracted)
        self.assertNotIn("color: red", extracted)
        self.assertNotIn("Home", extracted)  # Nav excluded
        self.assertIn("Position: Full Stack Engineer", extracted)
        self.assertIn("Build REST APIs with Node.js and TypeScript.", extracted)

    # --------------------------------------------------------------------------
    # 15. Valid Plain Text Extraction
    # --------------------------------------------------------------------------
    def test_15_valid_plain_text_extraction(self):
        utf8_text = "Role: Machine Learning Engineer\nLocation: Bengaluru\nSkills: Python, PyTorch, SQL"
        self.assertEqual(extract_text_from_txt(utf8_text.encode("utf-8")), utf8_text)

        latin1_text = "Role: Software Ingeniör\nSkills: C++, Linux"
        self.assertIn("Ingeni", extract_text_from_txt(latin1_text.encode("latin-1")))

    # --------------------------------------------------------------------------
    # 16. Authentication Required (401)
    # --------------------------------------------------------------------------
    def test_16_authentication_required(self):
        # 1. URL extraction unauthenticated
        res_url = client.post("/api/candidate/jd/extract-url", json={"url": "https://example.com/job"})
        self.assertEqual(res_url.status_code, 401)

        # 2. Upload unauthenticated
        res_upload = client.post(
            "/api/candidate/jd/upload",
            files={"file": ("jd.txt", b"Job text", "text/plain")}
        )
        self.assertEqual(res_upload.status_code, 401)

    # --------------------------------------------------------------------------
    # 17. Tenant Isolation (Authenticated Candidate Execution)
    # --------------------------------------------------------------------------
    def test_17_tenant_isolation(self):
        sample_html = "<html><body><h1>Role: DevOps Engineer</h1><p>Company: CloudBase</p><p>Experience: 3-5 years</p><p>Skills: Docker, Kubernetes, Terraform, AWS</p></body></html>"
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.headers = {"Content-Type": "text/html"}
        mock_res.encoding = "utf-8"
        mock_res.iter_content.return_value = [sample_html.encode("utf-8")]

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_res):
                res = client.post(
                    "/api/candidate/jd/extract-url",
                    headers=self.auth_headers,
                    json={"url": "https://careers.cloudbase.io/devops"}
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["status"], "extracted")
                self.assertEqual(data["normalized_jd"]["job_title"], "DevOps Engineer")
                self.assertEqual(data["normalized_jd"]["company"], "CloudBase")

    # --------------------------------------------------------------------------
    # 18. PDF Extraction
    # --------------------------------------------------------------------------
    def test_18_pdf_extraction(self):
        # Minimal mock PDF stream binary with BT ... ET text operator
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Length 58 >>\nstream\n"
            b"BT\n/F1 12 Tf\n(Job Title: Principal Architect) Tj\nET\n"
            b"endstream\nendobj\n%%EOF"
        )
        extracted = extract_text_from_pdf(pdf_bytes)
        self.assertIn("Principal Architect", extracted)

        doc_extracted = extract_text_from_document("architect_jd.pdf", pdf_bytes)
        self.assertIn("Principal Architect", doc_extracted)

    # --------------------------------------------------------------------------
    # 19. DOCX Extraction
    # --------------------------------------------------------------------------
    def test_19_docx_extraction(self):
        docx_buffer = io.BytesIO()
        with zipfile.ZipFile(docx_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body>
                    <w:p><w:r><w:t>Job Title: Lead Data Scientist</w:t></w:r></w:p>
                    <w:p><w:r><w:t>Company: DataMinds AI</w:t></w:r></w:p>
                    <w:p><w:r><w:t>Skills: Python, Spark, SQL, Machine Learning</w:t></w:r></w:p>
                </w:body>
            </w:document>"""
            zf.writestr("word/document.xml", document_xml)

        docx_bytes = docx_buffer.getvalue()
        extracted = extract_text_from_docx(docx_bytes)
        self.assertIn("Lead Data Scientist", extracted)
        self.assertIn("DataMinds AI", extracted)

        # Test upload API with DOCX
        res = client.post(
            "/api/candidate/jd/upload",
            headers=self.auth_headers,
            files={"file": ("job_spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["normalized_jd"]["job_title"], "Lead Data Scientist")
        self.assertEqual(data["normalized_jd"]["company"], "DataMinds AI")

    # --------------------------------------------------------------------------
    # 20. TXT Extraction
    # --------------------------------------------------------------------------
    def test_20_txt_extraction(self):
        raw_jd = (
            "Job Title: Site Reliability Engineer\n"
            "Company: InfraOps Global\n"
            "Location: Remote\n"
            "Experience: 4-6 years\n"
            "Requirements:\n"
            "- Kubernetes\n"
            "- Linux\n"
            "- Prometheus\n"
            "- Golang\n"
        )
        txt_bytes = raw_jd.encode("utf-8")
        extracted = extract_text_from_document("sre_jd.txt", txt_bytes)
        self.assertIn("Site Reliability Engineer", extracted)

        # Test upload API with TXT
        res = client.post(
            "/api/candidate/jd/upload",
            headers=self.auth_headers,
            files={"file": ("sre_jd.txt", txt_bytes, "text/plain")}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["normalized_jd"]["job_title"], "Site Reliability Engineer")
        self.assertEqual(data["normalized_jd"]["company"], "InfraOps Global")
        self.assertIn("Kubernetes", data["normalized_jd"]["tools"])

    # --------------------------------------------------------------------------
    # 21. Incomplete JD (No Hallucination or Fabrication)
    # --------------------------------------------------------------------------
    def test_21_incomplete_jd(self):
        sparse_text = "We are seeking a developer with Python skills."
        normalized = normalize_job_description(sparse_text, source_type="manual_paste")

        # Must extract the present skill
        self.assertIn("Python", normalized.required_skills)

        # Must NOT fabricate missing information
        self.assertIsNone(normalized.company)
        self.assertIsNone(normalized.location)
        self.assertIsNone(normalized.experience_required)
        self.assertIsNone(normalized.employment_type)
        self.assertIsNone(normalized.education_requirements)
        self.assertEqual(normalized.responsibilities, [])
        self.assertEqual(normalized.preferred_skills, [])
        self.assertEqual(normalized.domain_requirements, [])
        self.assertEqual(normalized.tools, [])

    # --------------------------------------------------------------------------
    # 22. Bot-Blocked Page Fallback (Cloudflare / CAPTCHA)
    # --------------------------------------------------------------------------
    def test_22_bot_blocked_page_fallback(self):
        bot_html = """
        <html>
        <head><title>Just a moment...</title></head>
        <body>
            <h1>Attention Required! | Cloudflare</h1>
            <p>Please complete the security check to continue</p>
            <p>Checking your browser before accessing the site.</p>
        </body>
        </html>
        """
        mock_bot_res = MagicMock()
        mock_bot_res.status_code = 200
        mock_bot_res.headers = {"Content-Type": "text/html"}
        mock_bot_res.encoding = "utf-8"
        mock_bot_res.iter_content.return_value = [bot_html.encode("utf-8")]

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.Session.get", return_value=mock_bot_res):
                success, status, msg, _ = safe_fetch_job_url("https://protected-job-board.com/careers/123")
                self.assertFalse(success)
                self.assertEqual(status, "fallback_required")
                self.assertTrue("bot verification" in msg.lower() or "captcha" in msg.lower())

                # Endpoint returns graceful fallback without HTTP 500
                res = client.post(
                    "/api/candidate/jd/extract-url",
                    headers=self.auth_headers,
                    json={"url": "https://protected-job-board.com/careers/123"}
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertFalse(data["success"])
                self.assertEqual(data["status"], "fallback_required")
                self.assertTrue(data["fallback_required"])
                self.assertIn("paste", data["message"].lower())


if __name__ == "__main__":
    unittest.main()
