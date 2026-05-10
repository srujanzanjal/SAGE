#!/usr/bin/env python3
"""
[DEPRECATED] SAGE GitHub Module QA Tests
This script has been superseded by test_qa_fast.py, which provides:
- Complete 15-question test (C), 3-mode test (D), 5-citation test (E)
- Session reuse for connection pool stability
- Proper timeout handling
- Repository overview chunk support

Use test_qa_fast.py instead:
    python test_qa_fast.py

This file is kept for reference only and is not actively maintained.
"""

import sys
sys.exit("Use test_qa_fast.py instead. This script is deprecated.")


# ========== TEST CATEGORY D: MODE BEHAVIOR TESTS ==========

def test_category_d(results):
    """Test mode behavior"""
    print("\n" + "="*60)
    print("TEST CATEGORY D: MODE BEHAVIOR TESTS")
    print("="*60)
    
    # D1: Irrelevant question in grounded mode
    print("\n[Test D1] Irrelevant Question (Grounded Mode)")
    session = requests.Session()
    try:
        result_d1 = ask_question(session, "What is the capital of Japan?", GITHUB_SOURCE_ID, "grounded")
    
    if result_d1.get("success"):
        confidence = result_d1.get("confidence", 0.0)
        answer = result_d1.get("answer", "")
        citations = result_d1.get("citations", [])
        
        if confidence < 0.3 and len(citations) < 2:
            results.add("D1", "Irrelevant Q in grounded", "grounded", confidence, len(citations) > 0, answer, "PASS", 
                       "Low confidence, no hallucination")
        else:
            results.add("D1", "Irrelevant Q in grounded", "grounded", confidence, len(citations) > 0, answer, "FAIL", 
                       f"Too high confidence ({confidence:.2f})")
    else:
        results.add("D1", "Irrelevant Q in grounded", "grounded", 0.0, False, "", "FAIL", result_d1.get("error"))
    
    # D2: Same question phrased differently
    print("\n[Test D2] Question Rephrasing")
    q2a = "Where is the main app defined?"
    q2b = "Which file starts the API server?"
    
        result_d2a = ask_question(session, q2a, GITHUB_SOURCE_ID, "grounded")
        result_d2b = ask_question(session, q2b, GITHUB_SOURCE_ID, "grounded")
    
    if result_d2a.get("success") and result_d2b.get("success"):
        conf_a = result_d2a.get("confidence", 0.0)
        conf_b = result_d2b.get("confidence", 0.0)
        cit_a = len(result_d2a.get("citations", []))
        cit_b = len(result_d2b.get("citations", []))
        
        # Check if confidence levels are similar (within 0.15)
        if abs(conf_a - conf_b) < 0.15:
            results.add("D2", "Q Rephrasing (similar)", "grounded", conf_a, cit_a > 0, 
                       result_d2a.get("answer", ""), "PASS", f"Similar confidence: {conf_a:.2f} vs {conf_b:.2f}")
        else:
            results.add("D2", "Q Rephrasing (similar)", "grounded", conf_a, cit_a > 0, 
                       result_d2a.get("answer", ""), "PARTIAL", f"Different confidence: {conf_a:.2f} vs {conf_b:.2f}")
    else:
        results.add("D2", "Q Rephrasing (similar)", "grounded", 0.0, False, "", "FAIL", "One or both queries failed")
    
    # D3: Vague question
    print("\n[Test D3] Vague Question")
        result_d3 = ask_question(session, "setup?", GITHUB_SOURCE_ID, "grounded")
    
    if result_d3.get("success"):
        confidence = result_d3.get("confidence", 0.0)
        citations = result_d3.get("citations", [])
        answer = result_d3.get("answer", "")
        
        if len(citations) > 0 or confidence > 0.2:
            results.add("D3", "Vague Q (setup?)", "grounded", confidence, len(citations) > 0, answer, "PASS", 
                       "Query rewrite helped find setup info")
        else:
            results.add("D3", "Vague Q (setup?)", "grounded", confidence, False, answer, "PARTIAL", 
                       "Low confidence, but no crash")
    else:
        results.add("D3", "Vague Q (setup?)", "grounded", 0.0, False, "", "FAIL", result_d3.get("error"))

# ========== TEST CATEGORY E: CITATION ACCURACY ==========

def test_category_e(results):
    """Test citation accuracy"""
    print("\n" + "="*60)
    print("TEST CATEGORY E: CITATION ACCURACY TESTS")
    print("="*60)
    
    # Ask 5+ questions and verify citations
        citation_questions = [
        "E1 - What is the project structure?",
        "E2 - List the main modules or directories",
        "E3 - What is the purpose of the main.py file?",
        "E4 - How are routes configured?",
        "E5 - What is in the requirements file?"
    ]
        
        for idx, question in enumerate(citation_questions):
            result = ask_question(session, question, GITHUB_SOURCE_ID, "grounded")
        
        if result.get("success"):
            citations = result.get("citations", [])
            answer = result.get("answer", "")
            
            if len(citations) > 0:
                # Check citation structure
                citation_valid = True
                for citation in citations:
                    file_path = citation.get("file_path", "")
                    start_line = citation.get("start_line")
                    end_line = citation.get("end_line")
                    snippet = citation.get("snippet", "")
                    
                    if not file_path or start_line is None or end_line is None or not snippet:
                        citation_valid = False
                        break
                
                if citation_valid and len(answer) > 20:
                    results.add(f"E{idx+1}", question, "grounded", result.get("confidence", 0.0), 
                               True, answer[:100], "PASS", f"{len(citations)} citations with correct structure")
                else:
                    results.add(f"E{idx+1}", question, "grounded", result.get("confidence", 0.0), 
                               True, answer[:100], "PARTIAL", f"{len(citations)} citations, structure check failed")
            else:
                results.add(f"E{idx+1}", question, "grounded", result.get("confidence", 0.0), 
                           False, answer[:100], "FAIL", "No citations provided")
            else:
                results.add(f"E{idx+1}", question, "grounded", 0.0, False, "", "FAIL", result.get("error"))

            if idx < len(citation_questions) - 1:
                time.sleep(1)
    finally:
        session.close()

def run_qa_tests():
    """Run all QA tests"""
    results = QATestResults()
    
    print("\n" + "="*70)
    print("SAGE GITHUB MODULE - QA & MODE & CITATION TESTS")
    print("="*70)
    
    test_category_c(results)
    test_category_d(results)
    test_category_e(results)
    
    summary = results.summary()
    return results, summary

if __name__ == "__main__":
    results, summary = run_qa_tests()
    print(f"\nTotal tests: {len(results.results)}")
    print(f"Results saved: {summary}")
