from bs4 import BeautifulSoup
import re
from typing import List, Dict, cast

def parse_textbook_content(html_content: str) -> str:
    """
    Parses raw textbook HTML (with Katex math) into a structured, readable text format.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # --- 1. CLEANUP & PRE-PROCESSING ---

    # Remove navigation elements (noise)
    for nav in soup.find_all(class_='navigation'):
        nav.decompose()

    # Process Math (Katex):
    # We want to replace the complex HTML span structure with the LaTeX annotation
    # found inside the <annotation encoding="application/x-tex"> tags.
    for katex_span in soup.find_all(class_='katex'):
        # Find the latex source inside
        annotation = katex_span.find('annotation', attrs={'encoding': 'application/x-tex'})
        if annotation:
            latex_text = annotation.get_text().strip()
            # Check if this was a display mode equation (usually in equation-block)
            is_display = 'display="block"' in str(katex_span) or katex_span.find('math', attrs={'display': 'block'})
            
            # Replace the entire katex span with the latex string
            if is_display:
                katex_span.replace_with(f"$$\n{latex_text}\n$$")
            else:
                katex_span.replace_with(f"${latex_text}$")
        else:
            # Fallback: just get text if no annotation found
            katex_span.replace_with(katex_span.get_text())

    # --- 2. EXTRACT STRUCTURED DATA ---

    # A. Student Location (Chapter/Section Title)
    location_header = soup.find('h1')
    location_text = location_header.get_text(strip=True) if location_header else "Unknown Location"
    
    # Try to parse Chapter/Section numbers from "2.1 Title"
    chapter_info = "Unknown"
    section_info = location_text
    match = re.match(r'(\d+)\.(\d+)\s+(.*)', location_text)
    if match:
        chapter_num, section_num, title = match.groups()
        chapter_info = chapter_num
        section_info = f"{chapter_num}.{section_num} — {title}"

    # B. Figures
    figures: List[Dict[str, str]] = []
    # Find figure containers
    for fig in soup.find_all(class_='figure-container'):
        img = fig.find('img')
        caption = fig.find(class_='figure-caption')
        
        src = cast(str, (img.get('src') or '')) if img else "No Source"
        caption_text = caption.get_text(strip=True) if caption else "No Caption"
        
        # Clean up relative paths for readability
        filename = src.split('/')[-1]
        
        figures.append({
            'id': filename,
            'description': caption_text
        })
        # Remove figure from DOM so it doesn't appear in the main text flow
        fig.decompose()

    # C. Main Text & Expandable Sections
    content_blocks: List[str] = []
    
    # We loop through specific content containers to maintain order
    # Targeting p, div.equation-block, and div.expandable-section
    for element in soup.find_all(['p', 'div']):
        classes = cast(List[str], element.get('class') or [])
        
        # skip if it was a figure or nav we already deleted/processed
        if element.parent is None: 
            continue

        if 'equation-block' in classes:
            # Clean up the equation number (e.g., "(2.1)")
            text = element.get_text(" ", strip=True)
            # Add some spacing for equations
            content_blocks.append(f"\n{text}\n")
            
        elif 'expandable-section' in classes:
            # Extract header and content from expandable sections (visualizations/extra explanations)
            header = element.find(class_='header-text')
            header_text = header.get_text(strip=True) if header else "Note"
            
            inner_content = element.find(class_='expand-content')
            inner_text = inner_content.get_text(" ", strip=True) if inner_content else ""
            
            # Format as a sidebar/note
            content_blocks.append(f"\n[SIDEBAR: {header_text}]\n{inner_text}\n")
            
        elif element.name == 'p':
            # Standard paragraphs
            # Only add if it's a direct child of body/main container (heuristic)
            # or if it hasn't been decomposed.
            text = element.get_text(" ", strip=True)
            if text:
                content_blocks.append(text)

    # --- 3. FORMAT OUTPUT ---

    output: List[str] = []
    
    # Header
    output.append("[STUDENT LOCATION]")
    output.append(f"Chapter: {chapter_info}")
    output.append(f"Section: {section_info}")
    output.append("")

    # Body
    output.append("[SECTION TEXT — AUTHORITATIVE]")
    for block in content_blocks:
        output.append(block)
    output.append("")

    # Figures
    output.append("[FIGURES — AUTHORITATIVE]")
    if figures:
        for fig in figures:
            output.append(f"{fig['description']}:")
            output.append(f"Filename: {fig['id']}")
            output.append("(Image attached)\n")
    else:
        output.append("No figures in this section.")
    
    # Join with newlines
    return "\n".join(output)
