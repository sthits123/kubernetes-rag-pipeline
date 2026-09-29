import logfire
import fitz  
MAX_CHARS_PER_PAGE = 50000


def parse_pdf(file_path: str) -> str:
    """
    Extract text from a PDF using PyMuPDF.

    Works well for normal/digital PDFs.
    Scanned PDFs with no text layer will require an OCR fallback.
    """

    with logfire.span("📄 PDF Parsing", filename=file_path):
        try:
            doc = fitz.open(file_path)

            total_pages = len(doc)
            logfire.info(f"Total pages: {total_pages}")

            pages = []

            for page_num, page in enumerate(doc):
                with logfire.span(
                    f"Processing page {page_num + 1}",
                    page=page_num + 1,
                ):
                    text = page.get_text("text")

                    if text.strip():
                        pages.append(text.strip())

            doc.close()

            full_text = "\n\n".join(pages)

            if not full_text.strip():
                logfire.warning(
                    f"⚠️ No text extracted from {file_path}. "
                    "PDF may be scanned/image-based."
                )
            else:
                logfire.info(
                    f"✅ PDF parsed successfully: "
                    f"{len(full_text)} characters"
                )

            return full_text

        except Exception as e:
            logfire.error(f"❌ PDF parsing failed: {e}")
            raise e