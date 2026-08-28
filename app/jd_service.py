"""
Job Description (JD) Ingestion & SSRF Defense Service Layer (Phase 5A)
Handles safe public URL fetching, document text extraction (PDF, DOCX, TXT),
and structured Job Description normalization with multi-layered SSRF guards.
"""

import re
import io
import json
import socket
import zipfile
import ipaddress
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple, Union

import requests
from app.models import NormalizedJobDescription


# ==============================================================================
# SSRF DEFENSE CONFIGURATION & IP BLOCKLISTING
# ==============================================================================

MAX_REDIRECTS = 3
CONNECT_TIMEOUT_SEC = 3.0
TOTAL_TIMEOUT_SEC = 5.0
MAX_RESPONSE_SIZE_BYTES = 1_572_864  # 1.5 MB

DISALLOWED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "instance-data",
    "169.254.169.254",
    "169.254.170.2",
    "0.0.0.0",
    "broadcast",
}

ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/json",
    "application/xhtml+xml",
    "text/xml",
    "application/xml",
)


class SSRFValidationError(Exception):
    """Raised when an outbound URL violates SSRF safety rules."""
    pass


def is_ip_restricted(ip_obj: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """
    Checks if an IP address falls into private, loopback, link-local, multicast,
    cloud metadata, CGNAT, benchmark, or reserved IP address spaces.
    """
    # If IPv6 is IPv4-mapped, check the mapped IPv4 address
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        return is_ip_restricted(ip_obj.ipv4_mapped)
    
    if (
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or ip_obj.is_reserved
    ):
        return True
    
    restricted_nets = [
        ipaddress.ip_network("100.64.0.0/10"),      # CGNAT (Carrier-grade NAT)
        ipaddress.ip_network("169.254.0.0/16"),     # Link Local / Cloud metadata
        ipaddress.ip_network("0.0.0.0/8"),          # Current network
        ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
        ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
        ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
        ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
        ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark testing
        ipaddress.ip_network("240.0.0.0/4"),        # Reserved for future use
        ipaddress.ip_network("255.255.255.255/32"), # Broadcast
        ipaddress.ip_network("fc00::/7"),           # IPv6 Unique Local
        ipaddress.ip_network("fe80::/10"),          # IPv6 Link-Local
        ipaddress.ip_network("ff00::/8"),           # IPv6 Multicast
    ]
    for net in restricted_nets:
        if ip_obj.version == net.version and ip_obj in net:
            return True
            
    ip_str = str(ip_obj)
    # Check known cloud metadata IPs explicitly
    if ip_str in ("169.254.169.254", "169.254.170.2", "100.100.100.200"):
        return True
        
    return False


def validate_and_resolve_url(url_str: str) -> Tuple[str, str, int]:
    """
    Validates URL scheme, hostname, and resolves DNS to ensure the destination
    does not point to loopback, private, link-local, cloud metadata, or multicast IP addresses.
    
    Returns:
        Tuple of (clean_url, resolved_ip, port)
    Raises:
        SSRFValidationError: if destination IP is private or restricted.
        ValueError: if URL format is invalid.
    """
    if not url_str or not isinstance(url_str, str):
        raise ValueError("URL cannot be empty.")
    
    url_str = url_str.strip()
    parsed = urllib.parse.urlparse(url_str)
    
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed.")
    
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a valid hostname.")
    
    hostname_clean = hostname.strip().lower().rstrip(".")
    
    # Check blocked hostname suffixes and exact disallowed hosts
    if (
        hostname_clean in DISALLOWED_HOSTS
        or "localhost" in hostname_clean
        or hostname_clean.endswith(".internal")
        or hostname_clean.endswith(".local")
        or hostname_clean.endswith(".localhost")
        or hostname_clean.endswith(".localdomain")
        or hostname_clean.endswith(".lan")
        or hostname_clean.endswith(".home")
        or hostname_clean.endswith(".corp")
        or hostname_clean.endswith(".arpa")
    ):
        raise SSRFValidationError(f"Access to localhost, internal network, or metadata host '{hostname_clean}' is forbidden.")
    
    # Check if hostname is direct IP literal (string, integer, hex)
    try:
        direct_ip = ipaddress.ip_address(hostname_clean)
        if is_ip_restricted(direct_ip):
            raise SSRFValidationError(f"Access to private or restricted network IP '{hostname_clean}' is forbidden.")
    except ValueError:
        pass
        
    # Check if hostname is integer representation of an IP (e.g. 2130706433)
    if hostname_clean.isdigit():
        try:
            int_ip = ipaddress.ip_address(int(hostname_clean))
            if is_ip_restricted(int_ip):
                raise SSRFValidationError(f"Access to private or restricted network IP '{hostname_clean}' is forbidden.")
        except (ValueError, OverflowError):
            pass

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    
    # Resolve DNS addresses
    try:
        addr_info = socket.getaddrinfo(hostname_clean, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as dns_err:
        raise ValueError(f"DNS lookup failed for hostname '{hostname_clean}': {dns_err}")
    except Exception as e:
        raise ValueError(f"Could not resolve host '{hostname_clean}': {e}")
    
    if not addr_info:
        raise ValueError(f"No IP addresses resolved for hostname '{hostname_clean}'.")
    
    resolved_ip_str = None
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFValidationError(f"Invalid IP address format resolved: '{ip_str}'")
        
        if is_ip_restricted(ip_obj):
            raise SSRFValidationError(f"Access to private or restricted network IP '{ip_str}' is forbidden.")
        
        if not resolved_ip_str:
            resolved_ip_str = ip_str
            
    return url_str, resolved_ip_str, port


# ==============================================================================
# HTML PARSER & TEXT EXTRACTION
# ==============================================================================

class HTMLTextExtractor(HTMLParser):
    """
    Strips script, style, nav, footer, header tags and extracts clean,
    structured paragraphs, headings, and bullet points.
    """
    def __init__(self):
        super().__init__()
        self._ignore_tags = {"script", "style", "noscript", "svg", "header", "footer", "nav", "iframe"}
        self._tag_stack = []
        self._text_chunks = []
        
    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        self._tag_stack.append(tag_lower)
        if tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section", "article"):
            self._text_chunks.append("\n")
        elif tag_lower == "br":
            self._text_chunks.append("\n")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()
        elif tag_lower in self._tag_stack:
            while self._tag_stack and self._tag_stack[-1] != tag_lower:
                self._tag_stack.pop()
            if self._tag_stack:
                self._tag_stack.pop()
        
        if tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self._text_chunks.append("\n")

    def handle_data(self, data):
        if not any(t in self._ignore_tags for t in self._tag_stack):
            text = data.strip()
            if text:
                self._text_chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._text_chunks)
        # Normalize repeated newlines and spaces
        cleaned = re.sub(r"[ \t]+", " ", raw)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


def extract_text_from_html(html_content: str) -> str:
    """Extracts human-readable Job Description text from HTML string."""
    if not html_content:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html_content)
        return parser.get_text()
    except Exception:
        # Fallback regex tag stripper if parser errors on malformed HTML
        stripped = re.sub(r"<script.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r"<style.*?</style>", "", stripped, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r"<[^>]+>", " ", stripped)
        return re.sub(r"\s+", " ", stripped).strip()


# ==============================================================================
# DOCUMENT PARSING (PDF, DOCX, TXT)
# ==============================================================================

def extract_text_from_txt(content_bytes: bytes) -> str:
    """Decodes plain text files with encoding fallbacks."""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return content_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return content_bytes.decode("utf-8", errors="ignore").strip()


def extract_text_from_docx(content_bytes: bytes) -> str:
    """Extracts text from DOCX (ZIP container with word/document.xml) using stdlib."""
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as docx_zip:
            if "word/document.xml" not in docx_zip.namelist():
                raise ValueError("Invalid DOCX format: missing word/document.xml")
            
            xml_content = docx_zip.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            
            paragraphs = []
            for p_tag in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                texts = [
                    t_tag.text for t_tag in p_tag.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                    if t_tag.text
                ]
                if texts:
                    paragraphs.append("".join(texts))
            
            return "\n".join(paragraphs).strip()
    except Exception:
        # Fallback text decode in case file was plain text or corrupt
        return extract_text_from_txt(content_bytes)


def extract_text_from_pdf(content_bytes: bytes) -> str:
    """Extracts text from PDF binary content using pypdf/pypdf2 or robust pure-python stream parsing."""
    if not content_bytes:
        return ""
    
    # Try pypdf or pypdf2 or pdfplumber if installed
    for lib in ("pypdf", "pypdf2", "pdfplumber"):
        try:
            if lib in ("pypdf", "pypdf2"):
                pdf_mod = __import__(lib)
                reader = pdf_mod.PdfReader(io.BytesIO(content_bytes))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                full_text = "\n".join(pages_text).strip()
                if full_text:
                    return full_text
            elif lib == "pdfplumber":
                pdf_mod = __import__(lib)
                with pdf_mod.open(io.BytesIO(content_bytes)) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages]
                    full_text = "\n".join(pages_text).strip()
                    if full_text:
                        return full_text
        except Exception:
            pass

    text_chunks = []
    # 1. Search for stream ... endstream blocks in PDF
    stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    for match in stream_pattern.finditer(content_bytes):
        raw_stream = match.group(1)
        # Attempt zlib decompression
        import zlib
        try:
            decompressed = zlib.decompress(raw_stream)
        except Exception:
            decompressed = raw_stream
        
        try:
            stream_str = decompressed.decode("latin-1", errors="ignore")
            # Extract strings inside parentheses (BT ... ET blocks)
            text_matches = re.findall(r"\(([^)]+)\)\s*T[jJ]", stream_str)
            if not text_matches:
                array_matches = re.findall(r"\[(.*?)\]\s*TJ", stream_str, re.DOTALL)
                for arr in array_matches:
                    inner_strs = re.findall(r"\(([^)]+)\)", arr)
                    if inner_strs:
                        text_matches.extend(inner_strs)
                        
            if text_matches:
                text_chunks.append(" ".join(text_matches))
        except Exception:
            pass
            
    if text_chunks:
        extracted = "\n".join(text_chunks).strip()
        if len(extracted) > 10:
            return extracted
    
    # 2. Fallback: Extract ASCII printable strings from PDF
    printable = re.findall(rb"[\x20-\x7E\r\n]{4,}", content_bytes)
    extracted = " ".join([
        p.decode("latin-1", errors="ignore")
        for p in printable
        if not p.startswith(rb"%PDF")
        and not p.startswith(rb"endobj")
        and not p.startswith(rb"xref")
        and not p.startswith(rb"trailer")
    ])
    return re.sub(r"\s+", " ", extracted).strip()


def extract_text_from_document(filename: str, content_bytes: bytes) -> str:
    """
    Routes document extraction based on file extension.
    Supports .pdf, .docx, .txt (and plain text).
    """
    fname_lower = filename.lower()
    if fname_lower.endswith(".pdf"):
        return extract_text_from_pdf(content_bytes)
    elif fname_lower.endswith(".docx") or fname_lower.endswith(".doc"):
        return extract_text_from_docx(content_bytes)
    else:
        return extract_text_from_txt(content_bytes)


# ==============================================================================
# SECURE URL FETCHER WITH MANUAL REDIRECT VALIDATION
# ==============================================================================

def safe_fetch_job_url(
    target_url: str,
    max_redirects: int = MAX_REDIRECTS,
    connect_timeout: float = CONNECT_TIMEOUT_SEC,
    total_timeout: float = TOTAL_TIMEOUT_SEC,
    max_bytes: int = MAX_RESPONSE_SIZE_BYTES,
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Safely fetches a public job description webpage with:
    - Pre-DNS SSRF validation
    - Hop-by-hop redirect re-validation
    - Content-Type enforcement
    - Maximum response streaming limits
    
    Returns:
        Tuple of (success, status, raw_text_or_error_message, final_url)
    """
    current_url = target_url
    redirect_count = 0
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    session = requests.Session()
    
    while redirect_count <= max_redirects:
        # Step 1: Pre-resolve and validate current URL
        try:
            clean_url, resolved_ip, port = validate_and_resolve_url(current_url)
        except SSRFValidationError as ssrf_err:
            return False, "ssrf_blocked", str(ssrf_err), current_url
        except ValueError as val_err:
            return False, "invalid_url", str(val_err), current_url
        
        # Step 2: Dispatch request with allow_redirects=False
        try:
            response = session.get(
                clean_url,
                headers=headers,
                timeout=(connect_timeout, total_timeout),
                stream=True,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return False, "fallback_required", "Connection timed out while fetching the job page. Please paste the JD text.", current_url
        except requests.exceptions.SSLError:
            return False, "fallback_required", "SSL certificate verification failed for job URL. Please paste the JD text.", current_url
        except requests.exceptions.ConnectionError:
            return False, "fallback_required", "Unable to connect to the target job server. Please paste the JD text.", current_url
        except Exception as req_err:
            return False, "fallback_required", f"Error connecting to job URL: {req_err}. Please paste the JD text.", current_url
        
        # Step 3: Handle HTTP Redirects manually with destination validation
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_count += 1
            if redirect_count > max_redirects:
                response.close()
                return False, "fallback_required", f"Job URL exceeded maximum redirect limit ({max_redirects} hops). Please paste the JD text.", current_url
            
            location = response.headers.get("Location")
            response.close()
            if not location:
                return False, "fallback_required", "Redirect header missing target Location. Please paste the JD text.", current_url
            
            next_url = urllib.parse.urljoin(current_url, location)
            current_url = next_url
            continue
        
        # Step 4: Handle HTTP Error Statuses gracefully
        if response.status_code in (401, 403):
            status_code = response.status_code
            response.close()
            return False, "fallback_required", f"Job posting requires authentication or is protected (HTTP {status_code}). Please copy and paste the JD text directly.", current_url
        elif response.status_code == 404:
            response.close()
            return False, "fallback_required", "Job posting page was not found (HTTP 404). Please paste the JD text.", current_url
        elif response.status_code >= 400:
            status_code = response.status_code
            response.close()
            return False, "fallback_required", f"Job server returned status {status_code}. Please paste the JD text.", current_url
        
        # Step 5: Content-Type Validation
        content_type_header = response.headers.get("Content-Type", "").lower()
        if content_type_header:
            main_type = content_type_header.split(";")[0].strip()
            if not any(main_type.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES):
                response.close()
                return False, "unsupported_content_type", f"Unsupported content type '{main_type}'. Please provide a web page URL or paste text.", current_url
        
        # Step 6: Check Content-Length header and stream content up to MAX_RESPONSE_SIZE_BYTES
        content_length_header = response.headers.get("Content-Length")
        if content_length_header:
            try:
                if int(content_length_header) > max_bytes:
                    response.close()
                    return False, "fallback_required", "Job posting page exceeded maximum allowable size (1.5 MB). Please paste the JD text.", current_url
            except ValueError:
                pass
                
        content_bytes = bytearray()
        is_oversized = False
        try:
            for chunk in response.iter_content(chunk_size=8192):
                content_bytes.extend(chunk)
                if len(content_bytes) > max_bytes:
                    is_oversized = True
                    break
        except Exception:
            pass
        finally:
            response.close()
        
        if is_oversized:
            return False, "fallback_required", "Job posting page exceeded maximum allowable size (1.5 MB). Please paste the JD text.", current_url

        encoding = response.encoding or "utf-8"
        try:
            raw_html = content_bytes.decode(encoding, errors="replace")
        except Exception:
            raw_html = content_bytes.decode("utf-8", errors="ignore")
        
        # Step 7: Bot protection / Cloudflare CAPTCHA detection
        captcha_signatures = [
            "checking your browser before accessing",
            "attention required! | cloudflare",
            "please complete the security check to continue",
            "enable javascript and cookies to continue",
            "verify you are human",
            "cf-chl-bypass",
            "challenge-running",
        ]
        html_lower = raw_html[:3000].lower()
        if any(sig in html_lower for sig in captcha_signatures) and len(raw_html) < 15000:
            return False, "fallback_required", "This job board is protected by automated bot verification / CAPTCHA. Please copy and paste the JD text directly.", current_url
        
        # Step 8: Parse text from HTML
        extracted_text = extract_text_from_html(raw_html)
        if not extracted_text or len(extracted_text.strip()) < 30:
            return False, "fallback_required", "Could not extract readable job text from this page. Please paste the JD text directly.", current_url
            
        return True, "extracted", extracted_text, current_url
    
    return False, "fallback_required", "Redirect limit reached. Please paste the JD text.", current_url


# ==============================================================================
# JD NORMALIZATION ENGINE (DETERMINISTIC EXTRACTION)
# ==============================================================================

COMMON_TECH_SKILLS = [
    "Python", "FastAPI", "Django", "Flask", "AsyncIO", "Java", "Spring Boot", "Kotlin",
    "Go", "Golang", "C++", "C#", ".NET", "Rust", "Node.js", "TypeScript", "JavaScript",
    "React", "React.js", "Vue", "Vue.js", "Angular", "Next.js", "GraphQL", "REST", "gRPC",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Cassandra", "DynamoDB", "Elasticsearch",
    "Kafka", "Apache Kafka", "RabbitMQ", "Celery", "Airflow", "Spark", "Hadoop", "Snowflake",
    "Docker", "Kubernetes", "K8s", "Terraform", "Ansible", "CI/CD", "GitHub Actions",
    "AWS", "Amazon Web Services", "GCP", "Google Cloud", "Azure", "Microservices",
    "System Design", "Distributed Systems", "Prometheus", "Grafana", "Linux", "SQL"
]

COMMON_DOMAINS = [
    "FinTech", "HealthTech", "B2B SaaS", "E-Commerce", "EdTech", "Artificial Intelligence",
    "Machine Learning", "Cloud Infrastructure", "Cybersecurity", "DevOps", "AdTech"
]


def normalize_job_description(
    raw_text: str,
    source_type: str = "manual_paste",
    source_url: Optional[str] = None
) -> NormalizedJobDescription:
    """
    Extracts and normalizes raw JD text into a standardized schema without fabricating missing information.
    Uses intelligent pattern extraction with zero external hallucinations.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if not raw_text or not raw_text.strip():
        return NormalizedJobDescription(
            source_type=source_type,
            source_url=source_url,
            fetched_at=now_iso
        )
    
    text = raw_text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    job_title = None
    company = None
    location = None
    experience_required = None
    employment_type = None
    education_requirements = None
    
    # 1. Job Title Extraction
    title_match = re.search(r"(?:Job Title|Position|Role|Opening):\s*([^\n\r,]+)", text, re.IGNORECASE)
    if title_match:
        job_title = title_match.group(1).strip()
    elif lines:
        for candidate_line in lines[:3]:
            if re.search(r"(Engineer|Developer|Designer|Manager|Lead|Architect|Specialist|Analyst|Scientist)", candidate_line, re.IGNORECASE):
                if len(candidate_line) < 80 and not candidate_line.lower().startswith("about") and not candidate_line.lower().startswith("company"):
                    job_title = candidate_line
                    break
    
    # 2. Company Name Extraction
    company_match = re.search(r"(?:Company|Employer|Organization):\s*([^\n\r,]+)", text, re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()
    else:
        about_match = re.search(r"About\s+([A-Z][A-Za-z0-9\s&]{2,30})", text)
        if about_match:
            company = about_match.group(1).strip()
            
    # 3. Location & Remote Status
    loc_match = re.search(r"(?:Location|Work Location|Place):\s*([^\n\r]+)", text, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()
    elif re.search(r"\b(Remote|Hybrid|On-site|San Francisco|New York|London|Bengaluru|Bangalore|Seattle|Austin)\b", text, re.IGNORECASE):
        loc_found = re.findall(r"\b(Remote|Hybrid|On-site|San Francisco|New York|London|Bengaluru|Bangalore|Seattle|Austin)\b", text, re.IGNORECASE)
        if loc_found:
            location = " / ".join(dict.fromkeys([l.title() for l in loc_found]))
            
    # 4. Experience Required
    exp_match = re.search(r"(\d+\s*[\+-]\s*\d*\s*(?:years?|yrs?)(?:\s+of\s+experience)?)", text, re.IGNORECASE)
    if exp_match:
        experience_required = exp_match.group(1).strip()
    elif re.search(r"\b(Senior|Staff|Principal|Lead|Junior|Entry Level|Mid-Level)\b", text, re.IGNORECASE):
        sen_match = re.search(r"\b(Senior|Staff|Principal|Lead|Junior|Entry Level|Mid-Level)\b", text, re.IGNORECASE)
        experience_required = f"{sen_match.group(1).title()} Level"
        
    # 5. Employment Type
    if re.search(r"\b(Full-time|Full Time|Permanent)\b", text, re.IGNORECASE):
        employment_type = "Full-time"
    elif re.search(r"\b(Contract|Contractor|Freelance)\b", text, re.IGNORECASE):
        employment_type = "Contract"
    elif re.search(r"\b(Part-time|Part Time)\b", text, re.IGNORECASE):
        employment_type = "Part-time"
    elif re.search(r"\b(Internship|Intern)\b", text, re.IGNORECASE):
        employment_type = "Internship"
        
    # 6. Education Requirements
    edu_match = re.search(r"(B\.?S\.?|M\.?S\.?|Bachelor'?s?|Master'?s?|Ph\.?D\.?|Computer Science Degree[^\n\r.]*)", text, re.IGNORECASE)
    if edu_match:
        education_requirements = edu_match.group(1).strip()
        
    # 7. Extract Skills (Required vs Preferred)
    required_skills = []
    preferred_skills = []
    
    pref_split = re.split(r"(?:Preferred|Nice to Have|Bonus|Plus|Optional|Good to Have)\s*:", text, flags=re.IGNORECASE)
    main_section = pref_split[0]
    pref_section = pref_split[1] if len(pref_split) > 1 else ""
    
    for skill in COMMON_TECH_SKILLS:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, main_section, re.IGNORECASE):
            if skill not in required_skills:
                required_skills.append(skill)
        elif pref_section and re.search(pattern, pref_section, re.IGNORECASE):
            if skill not in preferred_skills:
                preferred_skills.append(skill)
                
    # 8. Domain Requirements
    domain_requirements = []
    for dom in COMMON_DOMAINS:
        if re.search(rf"\b{re.escape(dom)}\b", text, re.IGNORECASE):
            domain_requirements.append(dom)
            
    # 9. Responsibilities Extraction (Bullet lines starting with -, *, •, or numbers)
    responsibilities = []
    bullet_pattern = re.compile(r"^\s*[-*•\d.]+\s*(.+)$", re.MULTILINE)
    for match in bullet_pattern.finditer(text):
        item = match.group(1).strip()
        if len(item) > 20 and not item.startswith("http"):
            responsibilities.append(item)
        if len(responsibilities) >= 10:
            break
            
    # 10. Tools Extraction
    tools_list = []
    tool_keywords = ["Docker", "Kubernetes", "Git", "GitHub", "GitLab", "Jira", "Terraform", "Ansible", "Linux", "Prometheus", "Grafana", "Postman"]
    for tool in tool_keywords:
        if re.search(rf"\b{re.escape(tool)}\b", text, re.IGNORECASE):
            tools_list.append(tool)
            
    # 11. Soft Skills
    soft_skills = []
    soft_keywords = ["Mentorship", "Leadership", "Communication", "Collaboration", "Problem Solving", "Agile", "Scrum"]
    for soft in soft_keywords:
        if re.search(rf"\b{re.escape(soft)}\b", text, re.IGNORECASE):
            soft_skills.append(soft)

    return NormalizedJobDescription(
        job_title=job_title,
        company=company,
        location=location,
        experience_required=experience_required,
        employment_type=employment_type,
        responsibilities=responsibilities,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        domain_requirements=domain_requirements,
        tools=tools_list,
        technical_requirements=[s for s in required_skills if s in ["Distributed Systems", "Microservices", "System Design", "AsyncIO", "gRPC", "REST"]],
        soft_skills=soft_skills,
        education_requirements=education_requirements,
        source_type=source_type,
        source_url=source_url,
        fetched_at=now_iso
    )
