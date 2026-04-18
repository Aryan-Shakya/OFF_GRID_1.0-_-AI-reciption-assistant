import re
import uuid
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from google import genai
from typing import Dict, List, Any

class EntityDetector:
    def __init__(self):
        # Broad keywords for "Ultra-General" reception intelligence
        self.categories = {
            "staff": [
                "professor", "director", "dean", "chair", "lecturer", "instructor",
                "associate", "assistant", "head", "faculty", "staff", "researcher",
                "manager", "coordinator", "officer", "president", "doctor", "physician",
                "specialist", "nurse", "ceo", "cto", "founder", "partner", "associate",
                "executive", "team", "personnel", "principal"
            ],
            "services": [
                "course", "program", "department", "curriculum", "treatment", "service",
                "surgery", "clinic", "product", "offering", "solution", "feature",
                "degree", "major", "minor", "specialization", "consultation", "therapy"
            ],
            "pricing": [
                "fee", "tuition", "cost", "price", "pricing", "charge", "payment",
                "scholarship", "financial aid", "billing", "insurance", "rate"
            ],
            "location": [
                "address", "location", "campus", "map", "direction", "office", "branch",
                "building", "room", "center", "venue"
            ],
            "policies": [
                "admission", "requirement", "policy", "term", "condition", "privacy",
                "refund", "cancellation", "rule", "regulation", "guideline", "eligibility"
            ],
            "contact": [
                "phone", "email", "contact", "call", "fax", "support", "help", "reach us"
            ]
        }
        self.name_titles = ["dr\\.", "mr\\.", "mrs\\.", "ms\\.", "prof\\.", "hon\\."]

    def identify_category(self, text: str) -> str:
        text_lower = text.lower()
        scores = {cat: 0 for cat in self.categories}
        
        for cat, keywords in self.categories.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[cat] += 1
        
        # Default to general if no strong matches
        best_cat = max(scores, key=scores.get)
        if scores[best_cat] == 0:
            return "general"
        return best_cat

class Extractor:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.entity_detector = EntityDetector()
        self.use_ai = self.config.get("use_ai", False)
        self.api_key = self.config.get("api_key") or self.config.get("gemini_api_key")
        
        if self.use_ai and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = 'gemini-1.5-flash'
            print(f"[Extractor] AI Mode Active using Gemini 1.5 Flash (google-genai)")

    def clean_text(self, text: str) -> str:
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove common noise patterns
        text = re.sub(r'(Read more|Click here|View details|Learn more)\.*', '', text, flags=re.IGNORECASE)
        return text

    def extract_facts(self, url: str, html: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove noise elements
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()

        raw_text = soup.get_text(separator=' ', strip=True)
        
        # If AI is enabled, try smart extraction first
        if self.use_ai and self.api_key:
            try:
                ai_facts = self._extract_with_ai(url, raw_text)
                if ai_facts:
                    return ai_facts
            except Exception as e:
                print(f"[Extractor] AI extraction failed, falling back to keywords: {e}")

        # Fallback to keyword-based extraction (Original Logic)
        facts = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
            text = self.clean_text(tag.get_text())
            if len(text) < 40:
                continue
            
            category = self.entity_detector.identify_category(text)
            facts.append({
                "id": str(uuid.uuid4())[:8],
                "category": category,
                "fact": text
            })

        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [self.clean_text(td.get_text()) for td in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append(" | ".join(cells))
            
            if rows:
                table_text = "Data Table: " + " ; ".join(rows)
                if len(table_text) > 50:
                    category = self.entity_detector.identify_category(table_text)
                    facts.append({
                        "id": str(uuid.uuid4())[:8],
                        "category": category,
                        "fact": table_text
                    })

        return facts

    def _extract_with_ai(self, url: str, text: str) -> List[Dict[str, str]]:
        # Limit text size to avoid token limits (GenAI 1.5 Flash has huge limit, but let's be safe/fast)
        truncated_text = text[:15000] 
        
        prompt = f"""
        You are a Reception Intelligence Agent. Your goal is to extract clear, atomic facts from the following website text for an AI Receptionist knowledge base.
        
        Website URL: {url}
        Text: {truncated_text}
        
        Extract information related to:
        1. Staff (Names, titles, emails, departments)
        2. Services/Offerings (What do they provide?)
        3. Pricing & Fees (If mentioned)
        4. Location & Contact (Addresses, phone numbers, hours)
        5. Policies (Admissions, refunds, rules)
        
        Guidelines:
        - Keep facts "atomic" (one clear piece of info per entry).
        - Rewrite facts to be natural and readable.
        - Categorize as one of: [staff, services, pricing, location, policies, general].
        - Return ONLY a valid JSON list of objects with "category" and "fact" fields.
        - Each object MUST have a unique 8-character string "id".
        
        Format:
        [
          {{"id": "...", "category": "staff", "fact": "Dr. John Doe is the Dean of Engineering."}},
          ...
        ]
        """
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        content = response.text.strip()
        
        # Strip markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        try:
            facts = json.loads(content)
            # Ensure facts are in the right format
            validated_facts = []
            for f in facts:
                if "fact" in f and "category" in f:
                    validated_facts.append({
                        "id": f.get("id", str(uuid.uuid4())[:8]),
                        "category": f["category"].lower(),
                        "fact": f["fact"]
                    })
            return validated_facts
        except Exception as e:
            print(f"Failed to parse AI response: {e}")
            return []

    # Keeping the original extract method signature for compatibility with CrawlerEngine for now, 
    # but it will now return a list of facts.
    def extract(self, url: str, html: str) -> Dict[str, Any]:
        facts = self.extract_facts(url, html)
        return {
            "url": url,
            "facts": facts
        }
