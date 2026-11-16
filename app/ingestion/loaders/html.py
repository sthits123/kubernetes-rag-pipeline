import logfire
from bs4 import BeautifulSoup

def parse_html(file_path: str):
    """
    Parses HTML content and extracts text.

    Args:
        file_path (str): The path to the HTML file to parse.

    Returns:
        str: The extracted text from the HTML content.
    """
    try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, "html.parser")
            
            # 1. Remove Junk (Scripts, Styles, Metadata)
            for script in soup(["script", "style", "meta", "noscript"]):
                script.decompose()
                
            # 2. Extract Text
            text = soup.get_text(separator="\n")
            
            # 3. Clean Whitespace (Collapse multiple newlines)
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text_clean = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text_clean
    
    except Exception as e:
            logfire.error(f"❌ HTML Parse Failed: {e}")
            raise e