#!/usr/bin/env python
"""Generate test PDF files for PDF module testing."""
import os
import fitz  # PyMuPDF


def create_valid_sage_test_pdf(output_path):
    """Create a valid 2-page PDF with SAGE-related content."""
    doc = fitz.open()
    
    # Page 1
    page1 = doc.new_page()
    page1_text = """SAGE stands for Semantic Analysis and Generation Engine. It is a source-grounded AI knowledge engine that supports Website Intelligence, PDF Intelligence, Video Intelligence, and GitHub Repository Intelligence."""
    page1.insert_textbox(
        page1.rect,
        page1_text,
        fontsize=12,
        color=(0, 0, 0),
    )
    
    # Page 2
    page2 = doc.new_page()
    page2_text = """The PDF module extracts selectable text using PyMuPDF, divides it into chunks, creates embeddings, stores metadata in Supabase, stores vectors in ChromaDB, and answers questions with page-level citations."""
    page2.insert_textbox(
        page2.rect,
        page2_text,
        fontsize=12,
        color=(0, 0, 0),
    )
    
    doc.save(output_path)
    doc.close()
    print(f"✓ Created: {output_path}")


def create_empty_pdf(output_path):
    """Create a PDF with blank pages and no selectable text."""
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(output_path)
    doc.close()
    print(f"✓ Created: {output_path}")


def create_image_only_pdf(output_path):
    """Create a PDF with only image content (no selectable text)."""
    try:
        from PIL import Image
        import io
        
        doc = fitz.open()
        page = doc.new_page()
        
        # Create a simple test image using PIL
        img = Image.new('RGB', (200, 200), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Insert image into PDF
        rect = fitz.Rect(50, 50, 250, 250)
        page.insert_image(rect, stream=img_bytes.read(), keep_ratio=True)
        
        doc.save(output_path)
        doc.close()
        print(f"✓ Created: {output_path}")
        return True
    except Exception as e:
        print(f"⚠ Could not create image-only PDF: {e}")
        return False


def create_unsupported_notes_txt(output_path):
    """Create a plain text file for unsupported type testing."""
    with open(output_path, 'w') as f:
        f.write("This is not a PDF.")
    print(f"✓ Created: {output_path}")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    create_valid_sage_test_pdf(os.path.join(base_dir, "valid_sage_test.pdf"))
    create_empty_pdf(os.path.join(base_dir, "empty_test.pdf"))
    image_created = create_image_only_pdf(os.path.join(base_dir, "image_only_test.pdf"))
    create_unsupported_notes_txt(os.path.join(base_dir, "unsupported_notes.txt"))
    
    print("\nTest assets generated successfully.")
