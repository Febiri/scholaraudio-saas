import sys
import os
import io
sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient
from backend.main import app
try:
    import pypdf
except (ImportError, Exception):
    pypdf = None

try:
    import fitz
except (ImportError, Exception):
    fitz = None

client = TestClient(app)

def create_mock_pdf() -> bytes:
    if fitz is not None:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "ProfFeb Research Benchmark: Scalable Multimodal Neural Transformers\n\nAbstract:\nWe present a scalable methodology for neural audio synthesis and mathematical formula deconstruction in scholarly literature.")
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
    
    # Standalone valid PDF with readable text stream
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 72 >> stream\n"
        b"BT /F1 12 Tf 50 700 Td (ProfFeb Research Benchmark: Neural Transformers) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000366 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n445\n%%EOF\n"
    )

def test_all():
    print("1. Testing HTML routes...")
    routes = ['/', '/conferences', '/app', '/radar', '/reviewer', '/grants', '/lab-connector', '/agent']
    for r in routes:
        resp = client.get(r)
        assert resp.status_code == 200, f"Route {r} failed with status {resp.status_code}"
        print(f"  [PASS] {r} -> {resp.status_code} ({len(resp.text)} bytes)")

    print("\n2. Testing SaaS Configuration Endpoint (/api/config)...")
    resp = client.get('/api/config')
    assert resp.status_code == 200, f"/api/config failed: {resp.text}"
    cfg = resp.json()
    assert cfg.get('app_name') == 'ProfFeb', f"Expected ProfFeb, got {cfg.get('app_name')}"
    assert 'supabase_url' in cfg, "Missing supabase_url"
    assert len(cfg.get('available_voices', [])) > 0, "Missing available_voices"
    print(f"  [PASS] /api/config verified: {cfg['app_name']} - {cfg['tagline']}")

    print("\n3. Testing Auth Me Endpoint (/api/auth/me)...")
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200, f"/api/auth/me failed: {resp.text}"
    auth_data = resp.json()
    assert 'authenticated' in auth_data, "Missing authenticated key"
    print(f"  [PASS] /api/auth/me verified: authenticated={auth_data['authenticated']}")

    print("\n4. Testing /api/reviewer/simulate...")
    resp = client.post('/api/reviewer/simulate', json={
        'title': 'Test Paper on Efficient Attention',
        'abstract': 'We introduce a low rank attention mechanism for transformers.',
        'target_venue': 'NeurIPS / IEEE'
    })
    assert resp.status_code == 200, f"/api/reviewer/simulate failed: {resp.text}"
    data = resp.json()
    assert 'overall_score' in data, 'Missing overall_score'
    print(f"  [PASS] /api/reviewer/simulate returned score {data['overall_score']}")

    print("\n5. Testing /api/radar/analyze...")
    resp = client.post('/api/radar/analyze', json={
        'topic': 'Graph Neural Network Compression',
        'idea_proposal': 'Quantizing GNN weight tensors using Hessian information'
    })
    assert resp.status_code == 200, f"/api/radar/analyze failed: {resp.text}"
    data = resp.json()
    assert 'novelty_score' in data, 'Missing novelty_score'
    print(f"  [PASS] /api/radar/analyze returned novelty score: {data['novelty_score']}%")

    print("\n6. Testing PDF Upload & Reviewer Audit with Synthetic PDF...")
    pdf_bytes = create_mock_pdf()
    resp = client.post(
        '/api/reviewer/upload-pdf',
        files={'file': ('mock_paper.pdf', io.BytesIO(pdf_bytes), 'application/pdf')},
        data={'target_venue': 'NeurIPS / IEEE'}
    )
    assert resp.status_code == 200, f"/api/reviewer/upload-pdf failed: {resp.text}"
    rev_data = resp.json()
    assert rev_data.get('success') is True, "Upload audit failed"
    print(f"  [PASS] /api/reviewer/upload-pdf processed mock paper successfully")

    print("\n7. Testing /api/conferences/featured & watchlist...")
    resp = client.get('/api/conferences/featured')
    assert resp.status_code == 200
    print(f"  [PASS] /api/conferences/featured returned valid response")

    resp = client.post('/api/conferences/watchlist', json={
        'conference_name': 'International Conference on Machine Learning',
        'acronym': 'ICML',
        'core_rank': 'A*',
        'submission_deadline': 'January 2027',
        'location': 'Vienna, Austria'
    })
    assert resp.status_code == 200
    wl_item = resp.json().get('item')
    print(f"  [PASS] /api/conferences/watchlist added {wl_item['acronym']}")

    resp = client.get('/api/conferences/watchlist')
    assert resp.status_code == 200
    assert resp.json().get('total') >= 1
    print(f"  [PASS] /api/conferences/watchlist retrieved {resp.json().get('total')} items")

    print("\n8. Testing Engine 07: Academic Co-Pilot & Profile...")
    resp = client.get('/api/twin/profile')
    assert resp.status_code == 200
    profile = resp.json()
    assert 'name' in profile, "Missing name in profile"
    print(f"  [PASS] /api/twin/profile verified: {profile['name']} ({profile.get('title', '')})")

    print("\n9. Testing Health Check Endpoint (/api/health)...")
    resp = client.get('/api/health')
    assert resp.status_code == 200
    health = resp.json()
    assert health.get('service') == 'ProfFeb', f"Expected ProfFeb, got {health.get('service')}"
    print(f"  [PASS] /api/health returned service={health['service']}")

    print("\nALL SAAS TEST SUITES PASSED FLAWLESSLY! 100% OPERATIONAL!")

if __name__ == '__main__':
    test_all()
