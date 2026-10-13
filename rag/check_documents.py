from pathlib import Path
from pypdf import PdfReader
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "railway_documents"


def extract_text(file_path):
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    if extension in (".html", ".htm"):
        html = file_path.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        soup = BeautifulSoup(html, "html.parser")

        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        return soup.get_text(separator="\n", strip=True)

    return ""


def main():
    if not DOCUMENTS_DIR.exists():
        print(f"Folder not found: {DOCUMENTS_DIR}")
        return

    files = sorted(
        file for file in DOCUMENTS_DIR.iterdir()
        if file.is_file()
        and file.suffix.lower() in {".pdf", ".html", ".htm"}
    )

    if not files:
        print("No PDF or HTML files found.")
        return

    print(f"Documents folder: {DOCUMENTS_DIR}")
    print(f"Total files: {len(files)}")

    for file_path in files:
        print("\n" + "=" * 60)
        print(f"FILE: {file_path.name}")

        try:
            text = extract_text(file_path)
            print(f"Extracted characters: {len(text)}")
            print("Preview:")
            print(text[:350] if text.strip() else "NO TEXT EXTRACTED")

        except Exception as error:
            print(f"ERROR: {error}")


if __name__ == "__main__":
    main()