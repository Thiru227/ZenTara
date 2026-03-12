import os
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path):
    """Extract text from PDF using PyMuPDF, page by page."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append({
                'page_number': page_num + 1,
                'text': text.strip()
            })
        doc.close()
        return {
            'success': True,
            'pages': pages,
            'page_count': len(pages),
            'full_text': '\n\n'.join([p['text'] for p in pages])
        }
    except ImportError:
        logger.warning("PyMuPDF not installed, using fallback text extraction")
        return _fallback_text_extraction(file_path)
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return {'success': False, 'error': str(e), 'pages': [], 'page_count': 0, 'full_text': ''}


def _fallback_text_extraction(file_path):
    """Fallback extraction when PyMuPDF isn't available."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        # Basic text extraction from PDF binary
        text = content.decode('latin-1', errors='ignore')
        # Filter printable characters
        readable = ''.join(c for c in text if c.isprintable() or c in '\n\t ')
        return {
            'success': True,
            'pages': [{'page_number': 1, 'text': readable[:5000]}],
            'page_count': 1,
            'full_text': readable[:5000]
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'pages': [], 'page_count': 0, 'full_text': ''}


def get_pdf_info(file_path):
    """Get basic PDF metadata."""
    try:
        import fitz
        doc = fitz.open(file_path)
        info = {
            'page_count': len(doc),
            'title': doc.metadata.get('title', ''),
            'author': doc.metadata.get('author', ''),
            'file_size': os.path.getsize(file_path)
        }
        doc.close()
        return info
    except Exception:
        return {
            'page_count': 0,
            'title': '',
            'author': '',
            'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
