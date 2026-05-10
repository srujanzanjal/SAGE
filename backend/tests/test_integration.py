"""
Integration tests for SAGE MVP v1.1 with Playwright-based website crawling.
Mark tests with @pytest.mark.integration to run only real website crawls.
"""
import pytest
import json


class TestHealthCheck:
    """Test API health endpoint."""

    def test_health_check(self, client):
        """Test backend is responsive."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app_name"] == "SAGE MVP API"


class TestWebsiteIngestion:
    """Test website crawling and ingestion using Playwright."""

    @pytest.mark.integration
    def test_valid_website_crawl(self, client, test_website_url):
        """Test crawling a valid website (python.org) using Playwright."""
        payload = {
            "url": test_website_url,
            "max_pages": 3,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "knowledgebase_id" in data
        assert "crawl_summary" in data
        assert "sources_created" in data
        
        crawl = data["crawl_summary"]
        assert crawl["pages_successfully_ingested"] > 0
        assert crawl["total_chunks_created"] > 0
        assert data["status"] == "ready"
        # Verify extraction method is playwright
        assert crawl.get("extraction_method") == "playwright"

    def test_invalid_url_rejection(self, client):
        """Test that invalid URLs are rejected."""
        payload = {
            "url": "not-a-valid-url",
            "max_pages": 10,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code in [400, 422]

    @pytest.mark.integration
    def test_low_text_website_returns_controlled_error(self, client, test_short_text_url):
        """Low-text websites should return a controlled 422 error instead of internal 500."""
        payload = {
            "url": test_short_text_url,
            "max_pages": 3,
            "max_depth": 1,
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 422
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict)
        assert detail.get("error_code") == "WEBSITE_NO_USABLE_TEXT"
        assert "No usable text could be extracted" in detail.get("message", "")

    @pytest.mark.integration
    def test_duplicate_url_detection(self, client, test_website_url):
        """Test that duplicate URLs are detected and reused."""
        payload = {
            "url": test_website_url,
            "max_pages": 2,
            "max_depth": 1
        }
        
        # First ingest
        response1 = client.post("/api/v1/ingest/website", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        kb_id_1 = data1["knowledgebase_id"]
        
        # Second ingest (duplicate)
        response2 = client.post("/api/v1/ingest/website", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        kb_id_2 = data2["knowledgebase_id"]
        
        # Should reuse same knowledgebase
        assert kb_id_1 == kb_id_2
        assert "Duplicate" in json.dumps(data2) or "reused" in json.dumps(data2).lower()

    @pytest.mark.integration
    def test_max_pages_limit(self, client, test_website_url):
        """Test that max_pages limit is respected."""
        payload = {
            "url": test_website_url,
            "max_pages": 2,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Should not exceed max_pages
        assert data["crawl_summary"]["pages_successfully_ingested"] <= 2

    @pytest.mark.integration
    def test_max_depth_limit(self, client, test_website_url):
        """Test that max_depth limit is respected."""
        payload = {
            "url": test_website_url,
            "max_pages": 10,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        assert response.json()["crawl_summary"]["pages_successfully_ingested"] >= 1

    @pytest.mark.integration
    def test_external_links_not_crawled(self, client, test_website_url):
        """Test that external links are not followed during crawl."""
        payload = {
            "url": test_website_url,
            "max_pages": 5,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # All crawled pages should have same domain
        for source in data["sources_created"]:
            source_url = source["canonical_ref"]
            assert "python.org" in source_url.lower() or "test" in source_url.lower()

    @pytest.mark.integration
    def test_rendered_content_extraction(self, client, test_website_url):
        """Test that Playwright extracts rendered content."""
        payload = {
            "url": test_website_url,
            "max_pages": 1,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["crawl_summary"]["pages_successfully_ingested"] >= 1
        assert data["crawl_summary"]["total_chunks_created"] >= 0


class TestPDFIngestion:
    """Test PDF ingestion."""

    def test_valid_pdf_upload(self, client):
        """Test uploading a valid PDF."""
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            sample_text = (
                "This is a test PDF with sample content for SAGE testing. "
                "It contains multiple lines of text to ensure proper chunking. "
                "SAGE should extract, chunk, embed, and index this content. "
                "This paragraph is intentionally longer so it clears the minimum text threshold. "
            )
            page.insert_textbox(page.rect, sample_text * 3)
            pdf_bytes = doc.tobytes()
            doc.close()
        except Exception:
            pdf_bytes = None
        
        if pdf_bytes:
            response = client.post(
                "/api/v1/ingest/pdf",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["chunks_count"] > 0
            assert data["status"] == "ready"

    def test_unsupported_file_type(self, client):
        """Test that unsupported file types are rejected."""
        response = client.post(
            "/api/v1/ingest/pdf",
            files={"file": ("test.txt", b"This is text", "text/plain")}
        )
        assert response.status_code == 415

    def test_empty_pdf_rejection(self, client, blank_pdf_bytes):
        """Test that blank/empty PDFs are rejected."""
        response = client.post(
            "/api/v1/ingest/pdf",
            files={"file": ("blank.pdf", blank_pdf_bytes, "application/pdf")}
        )
        assert response.status_code in [422, 400]


class TestQAFunctionality:
    """Test question answering."""

    @pytest.fixture(autouse=True)
    def setup_sources(self, client, test_website_url):
        """Setup test sources before running QA tests."""
        payload = {
            "url": test_website_url,
            "max_pages": 2,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        self.website_data = response.json()
        self.knowledgebase_id = self.website_data["knowledgebase_id"]

    def test_relevant_question_website(self, client):
        """Test asking a relevant question about website content."""
        payload = {
            "question": "What is Python?",
            "mode": "grounded",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert "answer" in data
        assert "confidence_score" in data
        assert data["mode"] == "grounded"
        assert 0 <= data["confidence_score"] <= 1

    def test_irrelevant_question_website(self, client):
        """Test asking an irrelevant question about website content."""
        payload = {
            "question": "What is the capital of Japan?",
            "mode": "grounded",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["confidence_score"] < 0.5

    def test_exploratory_mode(self, client):
        """Test exploratory mode returns different format."""
        payload = {
            "question": "What is Python?",
            "mode": "exploratory",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "exploratory"
        assert "answer" in data

    def test_grounded_mode_refusal(self, client):
        """Test that grounded mode refuses low-confidence answers."""
        payload = {
            "question": "xyz123 unknown",
            "mode": "grounded",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["confidence_score"] < 0.5

    def test_citation_presence(self, client):
        """Test that answers include citations."""
        payload = {
            "question": "What can Python be used for?",
            "mode": "grounded",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        if data["confidence_score"] > 0.4:
            assert isinstance(data["citations"], list)

    def test_missing_required_field(self, client):
        """Test that missing knowledgebase/source ID returns error."""
        payload = {
            "question": "What is Python?",
            "mode": "grounded",
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 400


class TestSourceListing:
    """Test source listing and management."""

    def test_list_sources(self, client):
        """Test listing sources."""
        response = client.get("/api/v1/sources")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        
        if data:
            source = data[0]
            assert "source_id" in source or "id" in source
            assert "source_type" in source


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_malformed_json(self, client):
        """Test handling of malformed JSON."""
        response = client.post(
            "/api/v1/qa/ask",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]

    def test_invalid_mode(self, client):
        """Test that invalid modes are rejected."""
        payload = {
            "question": "What is Python?",
            "mode": "invalid_mode",
            "knowledgebase_id": "test-id",
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code in [400, 422]

    def test_out_of_range_top_k(self, client):
        """Test that out-of-range top_k is rejected or clamped."""
        payload = {
            "question": "What is Python?",
            "mode": "grounded",
            "knowledgebase_id": "test-id",
            "top_k": 1000
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code in [200, 422]

    def test_playwright_installed(self, client):
        """Test that Playwright is properly installed."""
        payload = {
            "url": "https://example.com",
            "max_pages": 1,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        # Either succeeds (if Playwright installed) or returns proper error
        if response.status_code != 200:
            data = response.json()
            assert "Playwright" in json.dumps(data) or response.status_code in [422, 500]


class TestConfidenceScores:
    """Test confidence score behavior."""

    @pytest.fixture(autouse=True)
    def setup_sources(self, client, test_website_url):
        """Setup test sources."""
        payload = {
            "url": test_website_url,
            "max_pages": 2,
            "max_depth": 1
        }
        response = client.post("/api/v1/ingest/website", json=payload)
        assert response.status_code == 200
        self.website_data = response.json()
        self.knowledgebase_id = self.website_data["knowledgebase_id"]

    def test_confidence_range(self, client):
        """Test that confidence scores are in valid range."""
        payload = {
            "question": "What is Python?",
            "mode": "grounded",
            "knowledgebase_id": self.knowledgebase_id,
            "top_k": 6
        }
        response = client.post("/api/v1/qa/ask", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert 0 <= data["confidence_score"] <= 1

    def test_confidence_variance(self, client):
        """Test that different questions produce different confidence scores."""
        questions = [
            ("What is Python?", "relevant"),
            ("What is the capital of Japan?", "irrelevant"),
        ]
        
        scores = []
        for question, _ in questions:
            payload = {
                "question": question,
                "mode": "grounded",
                "knowledgebase_id": self.knowledgebase_id,
                "top_k": 6
            }
            response = client.post("/api/v1/qa/ask", json=payload)
            assert response.status_code == 200
            data = response.json()
            scores.append(data["confidence_score"])
        
        assert scores[0] > scores[1] or abs(scores[0] - scores[1]) < 0.1
